from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from pathlib import Path

class Siglip2VisualMemoryConfig(BaseModel):
    """Configuration for optional SigLIP2 visual memory retrieval during QA."""

    enabled: bool = Field(
        default=False,
        description="Whether to retrieve extra visual memory images with SigLIP2 during QA.",
    )
    image_root: Path = Field(
        default=Path("data") / Path("image"),
        description="Root directory containing the uuid/uid image folders for SigLIP2 retrieval.",
    )
    top_k: int = Field(
        default=4,
        description="Number of visual memory images to retrieve per question.",
    )
    model_id: str = Field(
        default="google/siglip2-base-patch16-224",
        description="Hugging Face model id used by SigLIP2 retrieval.",
    )
    batch_size: int = Field(
        default=16,
        description="Batch size used when embedding images for SigLIP2 retrieval.",
    )
    rebuild_index: bool = Field(
        default=False,
        description="Force rebuilding SigLIP2 image indexes instead of reusing cached ones.",
    )
    device: str = Field(
        default="cuda" if __import__("torch").cuda.is_available() else "cpu",
        choices=["cpu", "cuda"],
        description="Device used for SigLIP2 inference. Defaults to 'cuda' if available, otherwise 'cpu'.",
    )
    index_file: Path = Field(
        default=Path("data") / Path("tmp") / "siglip2_image_index.npz",
        description="Path to save/load cached SigLIP2 image embeddings. Should end with .npz.",
    )
