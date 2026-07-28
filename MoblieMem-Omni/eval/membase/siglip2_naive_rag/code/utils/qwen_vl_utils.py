"""Qwen-VL multimodal input token estimation and truncation utilities.

Combines two strategies:
1. Estimate image vision tokens via formula, drop images first when over budget.
2. Truncate text context (keep suffix = newest content) as fallback.
"""
from __future__ import annotations

import os
from math import ceil
from typing import TYPE_CHECKING, Any

from PIL import Image

if TYPE_CHECKING:
    from transformers import AutoProcessor

# Module-level processor cache (loaded at most once per process).
_PROCESSOR_CACHE: dict[str, "AutoProcessor | None"] = {}

# Default pixel bounds (Qwen3-VL defaults).
_DEFAULT_MIN_PIXELS = 256 * 28 * 28
_DEFAULT_MAX_PIXELS = 1280 * 28 * 28


def _load_processor(model_name: str) -> "AutoProcessor | None":
    """Lazy-load and cache the Qwen VL processor (tokenizer + image processor).

    Does **not** load model weights — only the lightweight processor config.
    Returns ``None`` if loading fails (caller should fall back to default pixel bounds).
    """
    if model_name in _PROCESSOR_CACHE:
        return _PROCESSOR_CACHE[model_name]
    try:
        from transformers import AutoProcessor as _AP

        processor = _AP.from_pretrained(model_name)
        _PROCESSOR_CACHE[model_name] = processor
        return processor
    except Exception as exc:
        print(f"[Qwen] Failed to load processor for {model_name}: {exc}. Using default pixel bounds.")
        _PROCESSOR_CACHE[model_name] = None
        return None


def estimate_image_tokens(image: Image.Image, processor: "AutoProcessor | None" = None) -> int:
    """Estimate the number of visual tokens an image will consume in Qwen-VL.

    Qwen divides the (potentially resized) image into 14×14 patches.
    Formula: ``ceil(h_scaled / 14) * ceil(w_scaled / 14) + 1`` (one global token).

    Args:
        image: PIL Image object (only ``.size`` is accessed; pixel data is not read).
        processor: Optional Qwen processor (provides ``min_pixels`` / ``max_pixels``).

    Returns:
        Estimated visual token count (>= 2).
    """
    width, height = image.size

    if processor is not None:
        img_proc = processor.image_processor
        max_pixels = getattr(img_proc.size, "get", lambda k, d: d)("max_pixels", _DEFAULT_MAX_PIXELS)
        min_pixels = getattr(img_proc.size, "get", lambda k, d: d)("min_pixels", _DEFAULT_MIN_PIXELS)
    else:
        max_pixels = _DEFAULT_MAX_PIXELS
        min_pixels = _DEFAULT_MIN_PIXELS

    pixels = width * height
    if pixels > max_pixels:
        scale = (max_pixels / pixels) ** 0.5
        width = int(width * scale)
        height = int(height * scale)
    elif pixels < min_pixels:
        scale = (min_pixels / pixels) ** 0.5
        width = int(width * scale)
        height = int(height * scale)

    grid_h = ceil(height / 14)
    grid_w = ceil(width / 14)
    return grid_h * grid_w + 1


def truncate_qwen(
    question: str,
    context: str,
    image_paths: list[str],
    *,
    processor: "AutoProcessor | None",
    max_total_tokens: int,
    reserve_for_output: int = 1024,
    no_image: bool = False,
    prompt_template: Any = None,
    data_root: str = "data",
) -> tuple[str, list[str]]:
    """Truncate Qwen-VL multimodal input to fit within a token budget.

    Priority:
    1. Drop images entirely (they consume the most tokens).
    2. Truncate text context from the **beginning** (keep suffix = newest content).

    Args:
        question: The question text.
        context: The retrieved memory context string.
        image_paths: Relative paths to image files.
        processor: Qwen AutoProcessor instance (used for its tokenizer).
        max_total_tokens: Total token budget (text + vision).
        reserve_for_output: Token count to reserve for model output.
        no_image: ``True`` if images will not be sent (``--no-image``).
        prompt_template: A ``string.Template`` (or anything with ``.substitute()``)
            used to count fixed-cost tokens (template scaffolding + question).
        data_root: Directory prepended to each relative image path.

    Returns:
        ``(truncated_context, kept_image_paths)``
    """
    max_input = max_total_tokens - reserve_for_output
    if max_input <= 0:
        return "", []

    # --- 0. Get the underlying tokenizer (processor may be AutoProcessor or a raw tokenizer) ---
    _tokenizer = processor.tokenizer if (processor is not None and hasattr(processor, 'tokenizer')) else processor

    # --- 1. Count fixed overhead (template scaffolding + question) ---
    if prompt_template is not None:
        prompt_fixed = prompt_template.substitute(question=question, context="")
    else:
        prompt_fixed = f"Question: {question}\nContext: "
    fixed_tokens = len(_tokenizer.encode(prompt_fixed)) if _tokenizer else 0

    # --- 2. Count context tokens ---
    context_tokens = _tokenizer.encode(context) if _tokenizer else []
    context_count = len(context_tokens)

    # --- 3. Count image tokens (estimated via formula) ---
    image_tokens = 0
    if not no_image and image_paths and _tokenizer is not None:
        for path in image_paths:
            full_path = os.path.join(data_root, path)
            if os.path.isfile(full_path):
                try:
                    img = Image.open(full_path)
                    image_tokens += estimate_image_tokens(img, processor)
                except Exception:
                    pass  # skip unreadable images

    total_text = fixed_tokens + context_count
    total = total_text + image_tokens

    if total <= max_input:
        return context, list(image_paths)

    kept = list(image_paths)

    # === Step 1: Drop images ===
    if not no_image and image_tokens > 0:
        total_no_img = total_text
        if total_no_img <= max_input:
            print(
                f"[Qwen Truncate] Dropped all images ({image_tokens} vision tokens). "
                f"Context: {context_count} tokens. Total: {total_no_img}/{max_input}"
            )
            return context, []  # dropping images was enough

        # Dropping images wasn't enough — proceed to text truncation.
        kept = []
        total = total_no_img
        print(
            f"[Qwen Truncate] Dropped images ({image_tokens} tokens) but text "
            f"still exceeds: {total}/{max_input}. Truncating text..."
        )

    # === Step 2: Truncate text context (keep suffix = newest content) ===
    allowed_context = max_input - fixed_tokens
    if allowed_context <= 0:
        context = ""
        print("[Qwen Truncate] Context fully dropped (budget consumed by template + question).")
    else:
        # Keep the beginning here
        truncated_tokens = context_tokens[:allowed_context]
        context = _tokenizer.decode(truncated_tokens) if _tokenizer else context
        print(f"[Qwen Truncate] Context: {context_count} -> {len(truncated_tokens)} tokens (kept prefix)")

    return context, kept
