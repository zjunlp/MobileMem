import argparse
import json
from pathlib import Path
from typing import Any
from typing import List, Sequence, Tuple

import numpy as np
import torch
from PIL import Image, UnidentifiedImageError
from transformers import AutoModel, AutoProcessor
import os
import time
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def to_feature_tensor(output) -> torch.Tensor:
    if isinstance(output, torch.Tensor):
        return output

    if hasattr(output, "image_embeds") and output.image_embeds is not None:
        return output.image_embeds

    if hasattr(output, "text_embeds") and output.text_embeds is not None:
        return output.text_embeds

    if hasattr(output, "pooler_output") and output.pooler_output is not None:
        return output.pooler_output

    if hasattr(output, "last_hidden_state") and output.last_hidden_state is not None:
        return output.last_hidden_state[:, 0]

    raise TypeError(f"Unsupported model output type: {type(output)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use Hugging Face SigLIP2 to vectorize images and run text-to-image retrieval."
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=Path("data") / Path("image"),
        help="Root directory containing images to index.",
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Text query used for retrieval.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top results to return.",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="google/siglip2-base-patch16-224",
        help="Hugging Face model id for SigLIP2.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size for image embedding.",
    )
    parser.add_argument(
        "--index-file",
        type=Path,
        default=Path("data/tmp/siglip2_image_index.npz"),
        help="Path to save/load cached image embeddings.",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force rebuilding index from images even if cache exists.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda" if torch.cuda.is_available() else "cpu",
        choices=["cpu", "cuda"],
        help="Device used for inference.",
    )
    return parser.parse_args()


def collect_images(image_root: Path) -> List[Path]:
    if not image_root.exists():
        raise FileNotFoundError(f"Image root does not exist: {image_root}")

    image_paths = [
        p
        for p in image_root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not image_paths:
        raise RuntimeError(f"No images found under: {image_root}")
    return sorted(image_paths)


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return vectors / norms


def load_image_rgb(path: Path) -> Image.Image:
    with Image.open(path) as img:
        return img.convert("RGB")


@torch.inference_mode()
def embed_images(
    model,
    processor,
    image_paths: Sequence[Path],
    batch_size: int,
    device: str,
) -> Tuple[List[Path], np.ndarray]:
    all_embeddings: List[np.ndarray] = []
    valid_paths: List[Path] = []

    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i : i + batch_size]

        images = []
        for path in batch_paths:
            try:
                images.append(load_image_rgb(path))
                valid_paths.append(path)
            except (UnidentifiedImageError, OSError):
                pass

        if not images:
            continue

        inputs = processor(images=images, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        features = model.get_image_features(**inputs)
        features = to_feature_tensor(features)
        features = torch.nn.functional.normalize(features, dim=-1)
        all_embeddings.append(features.detach().cpu().numpy())

    if not all_embeddings:
        raise RuntimeError("Unable to embed any images. Check image files and formats.")

    return valid_paths, np.vstack(all_embeddings).astype(np.float32)


@torch.inference_mode()
def embed_text(model, processor, query: str, device: str) -> np.ndarray:
    max_text_len = None
    text_config = getattr(getattr(model, "config", None), "text_config", None)
    if text_config is not None:
        max_text_len = getattr(text_config, "max_position_embeddings", None)
    if max_text_len is None:
        max_text_len = getattr(getattr(model, "config", None), "max_position_embeddings", None)
    if max_text_len is None:
        tokenizer = getattr(processor, "tokenizer", None)
        candidate = getattr(tokenizer, "model_max_length", None)
        if isinstance(candidate, int) and candidate > 0 and candidate < 1_000_000:
            max_text_len = candidate
    processor_kwargs = {
        "text": [query],
        "return_tensors": "pt",
        "padding": True,
        "truncation": True,
    }
    
    if max_text_len is not None and len(query) > max_text_len:
        if '？\nA.' in query:
            query = query.split('？\nA.')[0] + '?'
        elif 'A.' in query:
            query = query.split('A.')[0]
        else:
            #print("No suitable cut point found, truncating to max_text_len.")
            pass

    if isinstance(max_text_len, int) and max_text_len > 0:
        processor_kwargs["max_length"] = max_text_len

    inputs = processor(**processor_kwargs)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    features = model.get_text_features(**inputs)
    features = to_feature_tensor(features)
    features = torch.nn.functional.normalize(features, dim=-1)
    return features.detach().cpu().numpy().astype(np.float32)[0]


def save_index(index_file: Path, image_paths: Sequence[Path], image_embeddings: np.ndarray) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    path_array = np.array([str(p.as_posix()) for p in image_paths], dtype=object)
    np.savez_compressed(index_file, image_paths=path_array, image_embeddings=image_embeddings)


def load_index(index_file: Path) -> Tuple[List[Path], np.ndarray]:
    data = np.load(index_file, allow_pickle=True)
    image_paths = [Path(p) for p in data["image_paths"].tolist()]
    image_embeddings = data["image_embeddings"].astype(np.float32)
    return image_paths, l2_normalize(image_embeddings)


class Siglip2Searcher:
    def __init__(
        self,
        model_id: str = "google/siglip2-base-patch16-224",
        batch_size: int = 16,
        device: str | None = None,
        default_index_file_name: str = "siglip2_image_index.npz",
    ) -> None:
        self.model_id = model_id
        self.batch_size = batch_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.default_index_file_name = default_index_file_name
        self.model = AutoModel.from_pretrained(self.model_id).to(self.device)
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model.eval()
        self._index_cache: dict[tuple[str, str], tuple[List[Path], np.ndarray]] = {}

    def _resolve_index_file(
        self,
        image_root: Path,
        index_file: Path | None = None,
    ) -> Path:
        if index_file is not None:
            return Path(index_file)
        # Use centralized data/tmp for generated indices
        return Path("data") / Path("tmp") / self.default_index_file_name

    def _load_or_build_index(
        self,
        image_root: Path,
        *,
        index_file: Path | None = None,
        rebuild_index: bool = False,
        image_paths: list[Path] | None = None,
    ) -> tuple[List[Path], np.ndarray]:
        image_root = image_root.resolve()
        resolved_index_file = self._resolve_index_file(image_root, index_file).resolve()
        cache_key = (image_root.as_posix(), resolved_index_file.as_posix())

        if cache_key in self._index_cache and not rebuild_index:
            return self._index_cache[cache_key]

        if resolved_index_file.exists() and not rebuild_index and image_paths is None:
            image_paths, image_embeddings = load_index(resolved_index_file)
            self._index_cache[cache_key] = (image_paths, image_embeddings)
            return image_paths, image_embeddings

        if image_paths is None:
            image_paths = collect_images(image_root)
        image_paths, image_embeddings = embed_images(
            self.model, self.processor, image_paths, self.batch_size, self.device
        )
        save_index(resolved_index_file, image_paths, image_embeddings)
        self._index_cache[cache_key] = (image_paths, image_embeddings)
        return image_paths, image_embeddings

    @torch.inference_mode()
    def search(
        self,
        query: str,
        image_root: Path,
        top_k: int = 10,
        index_file: Path | None = None,
        rebuild_index: bool = False,
        image_paths: list[Path] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for images matching the text query.

        Args:
            query: Text query.
            image_root: Root directory containing images to search.
            top_k: Number of top results to return.
            index_file: Path to cached index file.
            rebuild_index: Force rebuilding index from images.
            image_paths: Optional list of specific image paths to search.
                         When provided, only these images are used (ignores index cache).

        Returns:
            List of dicts with 'path' (str) and 'score' (float) keys.
        """
        image_paths, image_embeddings = self._load_or_build_index(
            image_root,
            index_file=index_file,
            rebuild_index=rebuild_index,
            image_paths=image_paths,
        )

        query_embedding = embed_text(self.model, self.processor, query, self.device)

        scores = image_embeddings @ query_embedding
        top_k = min(top_k, len(image_paths))
        top_indices = np.argsort(-scores)[:top_k]

        results = []
        for i in top_indices:
            results.append({
                "path": image_paths[i].as_posix(),
                "score": float(scores[i]),
            })

        return results

    @torch.inference_mode()
    def search_from_index(
        self,
        query: str,
        image_paths: list[Path],
        image_embeddings: np.ndarray,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for images matching the text query using pre-built embeddings.

        Args:
            query: Text query.
            image_paths: List of image paths corresponding to the embeddings.
            image_embeddings: Pre-computed L2-normalized image embeddings (N, D).
            top_k: Number of top results to return.

        Returns:
            List of dicts with 'path' (str) and 'score' (float) keys.
        """
        query_embedding = embed_text(self.model, self.processor, query, self.device)

        scores = image_embeddings @ query_embedding
        top_k = min(top_k, len(image_paths))
        top_indices = np.argsort(-scores)[:top_k]

        results = []
        for i in top_indices:
            results.append({
                "path": image_paths[i].as_posix(),
                "score": float(scores[i]),
            })

        return results
