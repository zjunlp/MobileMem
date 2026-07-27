import json
import os
import re
from string import Template
from time import time
from pathlib import Path
from functools import partial
from litellm import token_counter as litellm_token_counter
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from ..datasets import DATASET_MAPPING
from ..inference_utils.operators import MultimodalQuestionAnsweringOperator
from ..model_types.dataset import QuestionAnswerPair
from ..model_types.memory import MemoryEntry
from typing import Any, Callable
from ..utils import get_tokenizer_for_model
from ..utils.visual_memory import VisualMemoryConfig


# ── Image map cache ──
_image_to_timestamp_map: dict[str, str] | None = None
_image_to_caption_map: dict[str, str] | None = None
_user_siglip2_index_cache: dict[str, tuple[list, Any]] = {}


def _load_timestamp_map() -> dict[str, str]:
    global _image_to_timestamp_map
    if _image_to_timestamp_map is None:
        with open("data/image_to_timestamp_map.json", encoding="utf-8") as f:
            _image_to_timestamp_map = json.load(f)
    return _image_to_timestamp_map


def _load_caption_map() -> dict[str, str]:
    global _image_to_caption_map
    if _image_to_caption_map is None:
        with open("data/image_to_caption_map.json", encoding="utf-8") as f:
            _image_to_caption_map = json.load(f)
    return _image_to_caption_map


def _append_visual_memory_section(
    context: str,
    visual_results: list[dict[str, Any]],
    retriever_name: str,
    count: int,
) -> str:
    if not visual_results:
        return context

    img2ts = _load_timestamp_map()
    img2cap = _load_caption_map()

    timestamps = ", ".join(
        img2ts.get(os.path.basename(r["path"]), "Timestamp not found")
        for r in visual_results
    )

    visual_lines = [
        "### VisualMemory:",
        f"The following images are retrieved as potentially relevant visual memories. The timestamps, in order, are: {timestamps}.",
    ]

    visual_block = "\n".join(visual_lines)
    if context:
        return f"{context}\n\n{visual_block}"
    return visual_block


def _load_user_siglip2_index(uid: str) -> tuple[list[Path], Any]:
    """Load the pre-built per-user SigLIP2 image index from ``data/tmp/{uid}_siglip2_index.npz``.

    ``uid`` is something like ``"u0"`` or ``"u66"``, matching the ``--user-id``
    CLI argument and the ``.npz`` file name produced by ``Raw2Locomo.py``.

    Caches the result in ``_user_siglip2_index_cache`` to avoid repeated I/O
    when the same user appears in multiple retrieval items.

    Returns:
        ``(image_paths, image_embeddings)`` — an empty pair if the index file
        does not exist.
    """
    global _user_siglip2_index_cache

    if uid in _user_siglip2_index_cache:
        return _user_siglip2_index_cache[uid]

    index_path = Path("data") / "tmp" / f"{uid}_siglip2_index.npz"
    if not index_path.exists():
        print(f"[WARNING] Pre-built siglip2 index not found: {index_path}")
        _user_siglip2_index_cache[uid] = ([], [])
        return [], []

    from ..utils.siglip2_search import load_index

    image_paths, image_embeddings = load_index(index_path)
    _user_siglip2_index_cache[uid] = (image_paths, image_embeddings)
    return image_paths, image_embeddings


def _find_visual_memory_images(
    uid: str,
    question: str,
    *,
    searcher: Any,
    top_k: int,
    retriever_name: str,
    count: int = 0,
) -> tuple[str, list[str]]:
    # Load pre-built per-user index (no directory scanning).
    image_paths, image_embeddings = _load_user_siglip2_index(uid)
    if not image_paths:
        print(f"[WARNING] No pre-built siglip2 index for uid '{uid}', skipping visual search.")
        return "", []

    try:
        results = searcher.search_from_index(
            query=question,
            image_paths=image_paths,
            image_embeddings=image_embeddings,
            top_k=top_k,
        )
    except Exception as exc:
        print(
            f"Error during visual search for uid '{uid}': "
            f"{exc.__class__.__name__}: {exc}"
        )
        return "", []

    if results:
        visual_context = _append_visual_memory_section(
            "",
            results,
            retriever_name,
            count,
        )
        visual_images = [result["path"] for result in results]
        return visual_context, visual_images

    return "", []


def _truncate_context(
    context: str,
    max_tokens: int,
    model: str,
) -> str:
    """Truncate a context string from the beginning if it exceeds ``max_tokens``.

    Keeps the suffix (newest content) since that is the most relevant portion
    for answering questions.

    Args:
        context: The assembled context string.
        max_tokens: Maximum allowed tokens for the context string.
        model: Model name used to select the tokenizer.

    Returns:
        The original context string if already within the limit,
        otherwise a truncated copy (suffix preserved).
    """
    if not context or max_tokens <= 0:
        return context

    tokenizer = get_tokenizer_for_model(model)
    counter = partial(litellm_token_counter, model=model, custom_tokenizer=tokenizer)
    total = counter(text=context)

    if total <= max_tokens:
        return context

    truncated = context
    ratio = (max_tokens / total) * 0.9
    cutoff = int(len(truncated) * ratio)
    truncated = truncated[:cutoff]

    print(
        f"[_truncate_context] {total} tokens -> truncated to "
        f"{counter(text=truncated)} tokens "
        f"(removed {len(context) - len(truncated)} chars from end)."
    )
    return truncated


def normalize_context_and_images(
    context_payload: Any,
) -> tuple[str, list[str]]:
    """Normalize legacy/custom context-builder outputs.

    Supported returns:
    - tuple[str, list[str] | str | None]
    - str
    """
    if isinstance(context_payload, tuple) and len(context_payload) == 2:
        context, image_payload = context_payload
    elif isinstance(context_payload, str):
        context, image_payload = context_payload, []
    else:
        raise TypeError(
            "context_builder must return either a context string or "
            "a tuple of (context, image_list)."
        )

    if context is None:
        context = ""
    if not isinstance(context, str):
        context = str(context)

    if image_payload is None:
        return context, []
    if isinstance(image_payload, str):
        return context, [image_payload]

    normalized_images: list[str] = []
    for img in image_payload:
        if isinstance(img, str) and img:
            normalized_images.append(img)
    return context, normalized_images


def default_context_builder(
    memories: list[MemoryEntry],
    include_image: bool = True,
) -> tuple[str, list[str]]:
    """Build context string and collect image paths from memories.

    Args:
        memories: List of retrieved memory entries.
        include_image: Whether to include image attachment markers.
    Returns:
        Tuple of (context_string, image_path_list)
    """
    parts = []

    img2ts = _load_timestamp_map()

    def _format_memory_text(mem: MemoryEntry, image_path_to_num: dict) -> str:
        base_text = mem.formatted_content or mem.content

        image_paths: list[str] = []
        if mem.image_path:
            image_paths = [mem.image_path] if isinstance(mem.image_path, str) else mem.image_path
            image_paths = [p for p in image_paths if isinstance(p, str) and p]

        # Nothing to add beyond base_text.
        if not image_paths or not include_image:
            return base_text

        image_lines = ["[Images attached details]"]
        for idx, path in enumerate(image_paths, start=1):
            global_img_num = image_path_to_num.get(path, "UNKNOWN")
            basename = os.path.basename(path)
            ts = img2ts.get(basename, "Timestamp not found")
            image_lines.append(f"- Image {global_img_num}: (attached below) Captured at {ts}")

        image_block = "\n".join(image_lines)

        replaced = re.sub(r"\[Images attached:\s*\d+\]", image_block, base_text)
        if replaced == base_text:
            return f"{base_text}\n{image_block}"
        return replaced

    seen_images = set()
    all_images = []

    for mem in memories:
        if mem.image_path:
            image_list = [mem.image_path] if isinstance(mem.image_path, str) else mem.image_path
            for img in image_list:
                if img not in seen_images:
                    seen_images.add(img)
                    all_images.append(img)

    image_path_to_num = {path: i+1 for i, path in enumerate(all_images)}

    for i, mem in enumerate(memories):
        parts.append(
            f"### Memory {i + 1}:\n{_format_memory_text(mem, image_path_to_num)}"
        )

    if include_image:
        return "\n\n".join(parts), all_images

    return "\n\n".join(parts), []


def answer_questions(
    retrievals: list[dict[str, Any]],
    qa_model: str,
    qa_batch_size: int = 4,
    add_question_timestamp: bool = False,
    prompt_template: Callable[[], Template] | None = None,
    context_builder: Callable[[list[MemoryEntry]], tuple[str, list[str]]] | None = None,
    include_image: bool = True,
    visual_memory_config: VisualMemoryConfig | None = None,
    interface_kwargs: dict[str, Any] | None = None,
    max_context_tokens: int | None = None,
    max_total_tokens: int | None = None,
    reserve_for_output: int = 1024,
    uid: str = "",
) -> list[dict[str, Any]]:
    """Answer questions using retrieved memories and an LLM.

    Args:
        retrievals (`list[dict[str, Any]]`):
            The retrieval results produced by the search runner.
        qa_model (`str`):
            Model name or path for question answering.
        qa_batch_size (`int`, defaults to `4`):
            Batch size for question-answering.
        add_question_timestamp (`bool`, defaults to `False`):
            Whether to append the question timestamp to the prompt.
        prompt_template (`Callable[[], Template] | None`, optional):
            A factory that returns a `string.Template` with
            `$question` and `$context` placeholders.
        context_builder (`Callable[[list[MemoryEntry]], str] | None`, optional):
            A callable that converts a list of memory entries into a single
            context string.
        interface_kwargs (`dict[str, Any] | None`, optional):
            Extra keyword arguments forwarded to the LLM operator.

    Returns:
        `list[dict[str, Any]]`:
            Raw LLM response dictionaries.
    """
    interface_kwargs = interface_kwargs or {}
    visual_memory_config = visual_memory_config or VisualMemoryConfig()

    if context_builder is None:
        from functools import partial
        context_builder = partial(default_context_builder, include_image=include_image)

    visual_memory_searcher = None
    if visual_memory_config.enabled:
        if visual_memory_config.retriever_type == "siglip2":
            from ..utils.siglip2_search import Siglip2Searcher

            visual_memory_searcher = Siglip2Searcher(
                model_id=visual_memory_config.model_id,
                batch_size=visual_memory_config.batch_size,
                device=visual_memory_config.device
            )
        elif visual_memory_config.retriever_type == "internvideo2":
            from ..utils.internvideo2_search import InternVideo2Searcher

            visual_memory_searcher = InternVideo2Searcher(
                model_id=visual_memory_config.model_id,
                batch_size=visual_memory_config.batch_size,
                device=visual_memory_config.device,
                trust_remote_code=visual_memory_config.trust_remote_code,
            )

    #if context_builder is None:
    #    context_builder = lambda memories: "\n\n".join(
    #        f"### Memory {i + 1}:\n{mem.formatted_content or mem.content}"
    #        for i, mem in enumerate(memories)
    #    )

    questions = []
    contexts = []
    images = []
    recall_start = 0

    # Operator must be created before the loop so its .prompt is available
    # for Qwen VL truncation (prompt_template is needed to count fixed tokens).
    qa_operator = MultimodalQuestionAnsweringOperator(
        prompt_name="structured-question-answering",
        model_name=qa_model,
        timeout=120.0,
        **interface_kwargs,
    )
    if prompt_template is not None:
        qa_operator.set_prompt(prompt_template())

    for item in retrievals:
        qa_pair = item["qa_pair"]
        question = qa_pair.question
        if "name" in qa_pair.metadata:
            question = f"{qa_pair.metadata['name']}: {question}"
        if add_question_timestamp:
            question += f"\nQuestion Timestamp:{qa_pair.timestamp}"
        question = f"[{qa_pair.question_format}] " + question
        questions.append(question)
        context_payload = context_builder(item["retrieved_memories"])
        context, image = normalize_context_and_images(context_payload)

        recall_start = len(image)

        # Only one retriever is used at a time, determined by visual_memory_config.retriever_type
        if visual_memory_searcher is not None and visual_memory_config.enabled:
            visual_context, visual_images = _find_visual_memory_images(
                uid,
                question,
                searcher=visual_memory_searcher,
                top_k=visual_memory_config.top_k,
                retriever_name=visual_memory_config.retriever_type,
                count=recall_start,
            )

            if visual_context:
                context = f"{context}\n\n{visual_context}" if context else visual_context
            if visual_images:
                existing_images = set(image)
                for visual_image in visual_images:
                    if visual_image not in existing_images:
                        existing_images.add(visual_image)
                        image.append(visual_image)

        # Truncate multimodal input for Qwen VL models.
        # Priority: drop images first, then truncate text (keep suffix).
        if "qwen" in qa_model.lower():
            qwen_budget = max_total_tokens or max_context_tokens
            if qwen_budget is not None:
                from ..utils.qwen_vl_utils import truncate_qwen, _load_processor

                qwen_processor = _load_processor("Qwen/Qwen3-VL-8B-Instruct")
                context, image = truncate_qwen(
                    question=questions[-1],
                    context=context,
                    image_paths=image,
                    processor=qwen_processor,
                    max_total_tokens=qwen_budget,
                    reserve_for_output=reserve_for_output,
                    no_image=not include_image,
                    prompt_template=qa_operator.prompt,
                )
        # Truncate plain-text context for non-Qwen models.
        elif max_context_tokens is not None:
            context = _truncate_context(context, max_context_tokens, qa_model)

        contexts.append(context)
        images.append(image)

    responses = qa_operator(
        questions,
        contexts,
        images,
        recall_start,
        batch_size=qa_batch_size,
        aggregate=False,
        temperature=0.0,
    )
    return responses


class EvaluationRunnerConfig(BaseModel):
    """Configuration for the evaluation runner."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    search_results_path: str = Field(
        ...,
        description="Path to the search results.",
    )
    dataset_type: str = Field(
        ...,
        description="The type of the dataset used to evaluate the memory layer.",
    )
    qa_model: str = Field(
        default="gpt-4.1-mini",
        description="Model name or path for question answering.",
    )
    judge_model: str = Field(
        default="gpt-4.1-mini",
        description="Model name or path for judgment.",
    )
    qa_batch_size: int = Field(
        default=4,
        description="Batch size for question-answering.",
    )
    judge_batch_size: int = Field(
        default=4,
        description="Batch size for judgment.",
    )
    api_config_path: str | None = Field(
        default=None,
        description="Path to the API config file.",
    )
    api_keys: list[str] | None = Field(
        default=None,
        description=(
            "API keys for the LLM operator. "
            "If provided, they take precedence over ``api_config_path``."
        ),
    )
    base_urls: list[str] | None = Field(
        default=None,
        description=(
            "Base URLs for the LLM operator. "
            "If provided, they take precedence over ``api_config_path``."
        ),
    )
    context_builder: Callable[[list[MemoryEntry]], tuple[str, list[str]]] | None = Field(
        default=None,
        description=(
            "A callable that converts a list of memory entries into a context string."
        ),
    )
    include_image: bool = Field(
        default=True,
        description="Whether to include base64-encoded images in the LLM request.",
    )
    visual_memory: VisualMemoryConfig = Field(
        default_factory=VisualMemoryConfig,
        description="Unified visual memory retrieval settings. Supports 'siglip2' and 'internvideo2' via retriever_type.",
    )
    prompt_template: Callable[[], Template] | None = Field(
        default=None,
        description=(
            "A factory that returns a ``string.Template`` with "
            "``$question`` and ``$context`` placeholders."
        ),
    )
    add_question_timestamp: bool = Field(
        default=False,
        description="Append the question timestamp to the prompt.",
    )
    max_context_tokens: int | None = Field(
        default=None,
        description=(
            "Maximum allowed tokens for the context string. "
            "If the built context exceeds this limit, it is truncated "
            "from the beginning (keeping the most recent content)."
        ),
    )
    max_total_tokens: int | None = Field(
        default=None,
        description=(
            "Maximum total tokens (text + vision) for Qwen VL models. "
            "If exceeded, images are dropped first; then context text is "
            "truncated from the beginning (keeping the most recent content)."
        ),
    )
    reserve_for_output: int = Field(
        default=1024,
        description=(
            "Token count reserved for model output when using "
            "``max_total_tokens`` with Qwen VL models."
        ),
    )
    multi_qa_batch_size: int = Field(
        default=1,
        description=(
            "When > 1, groups multiple questions into a single LLM call with "
            "shared context. The model must output a JSON array. "
            "Only recommended for baselines like long_context where all "
            "questions share the same context."
        ),
    )
    debug: bool = Field(
        default=False,
        description="Print full raw response on parse failure for debugging.",
    )
    stat_output_dir: str | None = Field(
        default=None,
        description=(
            "Custom directory name (relative to project root) for evaluation "
            "statistics. If set, stats are saved to ``{root_dir}/{stat_output_dir}/{user_id}/`` "
            "instead of the default ``{root_dir}/res/{user_id}/``."
        ),
    )
    save_intermediate: bool = Field(
        default=True,
        description=(
            "Whether to save the intermediate predictions file "
            "(`*_predictions.json`) alongside the final evaluation results."
        ),
    )


class EvaluationRunner:
    """Runner that orchestrates the question-answering and evaluation stage.

    It loads retrieval results, generates answers via an LLM, and then
    delegates judgment to the dataset-specific evaluation logic.
    """

    def __init__(self, config: EvaluationRunnerConfig) -> None:
        """Initialize the evaluation runner.

        Args:
            config (`EvaluationRunnerConfig`):
                The runner configuration.
        """
        self.config = config

    def _resolve_interface_kwargs(self) -> dict[str, Any]:
        """Build the interface keyword arguments for the LLM operator."""
        cfg = self.config
        interface_kwargs = {}
        # Set per-baseline debug output directory.
        search_dir = os.path.dirname(cfg.search_results_path)
        interface_kwargs["debug_output_dir"] = os.path.join(search_dir, "message_logs")

        if cfg.api_keys is not None and cfg.base_urls is not None:
            interface_kwargs["api_keys"] = cfg.api_keys
            interface_kwargs["base_urls"] = cfg.base_urls
        elif cfg.api_config_path is not None:
            with open(cfg.api_config_path, "r") as f:
                api_config = json.load(f)
            interface_kwargs["api_keys"] = api_config["api_keys"]
            interface_kwargs["base_urls"] = api_config["base_urls"]
        elif os.environ.get("OPENAI_API_KEY") is not None:
            interface_kwargs["api_keys"] = [os.environ["OPENAI_API_KEY"]]
            interface_kwargs["base_urls"] = [os.environ.get("OPENAI_API_BASE")]

        return interface_kwargs

    def extract_images_from_memories(memories: list[MemoryEntry]) -> list[str]:
        """从 MemoryEntry 中提取所有图像路径"""
        images = []
        for mem in memories:
            if mem.image_path:
                images.extend(mem.image_path)
        return images

    def run(self) -> list[dict[str, Any]]:
        """Execute the question-answering and evaluation pipeline.

        Returns:
            `list[dict[str, Any]]`:
                A list of evaluation results. Each element is a dictionary
                containing the question-answer pair, the prediction, the metrics,
                the retrieved memories, and the user id.
        """
        cfg = self.config
        interface_kwargs = self._resolve_interface_kwargs()
        dataset_cls = DATASET_MAPPING[cfg.dataset_type]

        # Load and deserialize retrieval results.
        with open(cfg.search_results_path, "r") as f:
            retrievals = json.load(f)
        for item in retrievals:
            item["qa_pair"] = QuestionAnswerPair(**item["qa_pair"])
            raw_memories = item["retrieved_memories"]
            item["retrieved_memories"] = []
            for mem in raw_memories:
                # Backward compat: old search results had image_cap as str
                if isinstance(mem.get("image_cap"), str):
                    mem["image_cap"] = [mem["image_cap"]]
                item["retrieved_memories"].append(MemoryEntry(**mem))
        print(
            f"✅ {len(retrievals)} retrieval results are loaded "
            f"from {cfg.search_results_path}."
        )

        # Derive uid (e.g. "u0", "u66") from the search results path.
        # Path pattern: $ROOT/output/{baseline}/shared/{uid}/{top_k}_0_1.json
        search_dir = os.path.dirname(cfg.search_results_path)
        uid = os.path.basename(search_dir)

        # Generate answers.
        print("🧠 Generating answers...")
        if cfg.multi_qa_batch_size > 1:
            from .long_context_evaluation import answer_long_context_questions

            qa_responses = answer_long_context_questions(
                retrievals,
                qa_model=cfg.qa_model,
                qa_batch_size=cfg.qa_batch_size,
                add_question_timestamp=cfg.add_question_timestamp,
                prompt_template=cfg.prompt_template,
                context_builder=cfg.context_builder,
                include_image=cfg.include_image,
                visual_memory_config=cfg.visual_memory,
                interface_kwargs=interface_kwargs,
                max_context_tokens=cfg.max_context_tokens,
                max_total_tokens=cfg.max_total_tokens,
                reserve_for_output=cfg.reserve_for_output,
                uid=uid,
                multi_qa_batch_size=cfg.multi_qa_batch_size,
                debug=cfg.debug,
            )
        else:
            qa_responses = answer_questions(
                retrievals,
                qa_model=cfg.qa_model,
                qa_batch_size=cfg.qa_batch_size,
                add_question_timestamp=cfg.add_question_timestamp,
                prompt_template=cfg.prompt_template,
                context_builder=cfg.context_builder,
                include_image=cfg.include_image,
                visual_memory_config=cfg.visual_memory,
                interface_kwargs=interface_kwargs,
                max_context_tokens=cfg.max_context_tokens,
                max_total_tokens=cfg.max_total_tokens,
                reserve_for_output=cfg.reserve_for_output,
                uid=uid,
            )

        # Extract prediction strings from raw LLM responses.
        predictions = []
        for resp in qa_responses:
            pred = resp.get("processed_content")
            if pred is None:
                raise ValueError(
                    "The question-answering model returns an empty prediction."
                )
            predictions.append(pred)

        # Save intermediate results (qa_pairs + predictions) for later judge stage.
        if cfg.save_intermediate:
            model_safe = cfg.qa_model.replace("/", "-").replace(".", "-")
            intermediate_path = cfg.search_results_path.rsplit(".", 1)[0] + f"_{model_safe}_predictions.json"
            intermediate_results = []
            for i, item in enumerate(retrievals):
                intermediate_results.append(
                    {
                        "qa_pair": item["qa_pair"].model_dump(mode="python"),
                        "prediction": predictions[i],
                        "retrieved_memories": [
                            mem.model_dump(mode="python")
                            for mem in item["retrieved_memories"]
                        ],
                        "user_id": item["user_id"],
                    }
                )
            with open(intermediate_path, "w", encoding="utf-8") as f:
                json.dump(
                    intermediate_results,
                    f,
                    ensure_ascii=False,
                    indent=4,
                )
            print(f"💾 Intermediate results (predictions only) saved to {intermediate_path}.")

        # Evaluate answers via the dataset class's judge logic.
        print("⚖️ Evaluating answers...")
        qa_pairs = [item["qa_pair"] for item in retrievals]
        judge_results = dataset_cls.evaluate(
            qa_pairs=qa_pairs,
            predictions=predictions,
            judge_model=cfg.judge_model,
            judge_batch_size=cfg.judge_batch_size,
            **interface_kwargs,
        )

        # Assemble final outputs.
        final_results = []
        for i, item in enumerate(retrievals):
            qa_pair = item["qa_pair"]
            final_results.append(
                {
                    "qa_pair": qa_pair.model_dump(mode="python"),
                    "prediction": predictions[i],
                    "metrics": judge_results[i],
                    "retrieved_memories": [
                        mem.model_dump(mode="python")
                        for mem in item["retrieved_memories"]
                    ],
                    "user_id": item["user_id"],
                }
            )

        # Persist results (add model name + suffix to prevent overwrites).
        model_safe = cfg.qa_model.replace("/", "-").replace(".", "-")
        suffix_parts = [model_safe]
        if not cfg.include_image:
            suffix_parts.append("noimage")
        suffix = "_" + "_".join(suffix_parts) if suffix_parts else ""
        output_path = (
            cfg.search_results_path.rsplit(".", 1)[0] + suffix + "_evaluation.json"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                final_results,
                f,
                ensure_ascii=False,
                indent=4,
            )
        print(f"✅ {len(final_results)} evaluation results are saved to {output_path}.")

        # ── Compute and save summary statistics ──
        metric_names = list(
            dict.fromkeys(
                key for result in final_results for key in result.get("metrics", {}).keys()
            )
        )

        stats: dict[str, Any] = {}
        for metric in metric_names:
            values = []
            for result in final_results:
                m = result.get("metrics", {}).get(metric, {})
                if isinstance(m, dict) and "value" in m:
                    values.append(m["value"])

            if values:
                stats[metric] = {
                    "overall": sum(values) / len(values),
                    "count": len(values),
                }

        # Per-question-type breakdown.
        question_type_groups: dict[str, list[int]] = {}
        for idx, result in enumerate(final_results):
            qtype = (
                result.get("qa_pair", {})
                .get("metadata", {})
                .get("question_type", "unknown")
            )
            question_type_groups.setdefault(qtype, []).append(idx)

        if question_type_groups:
            stats["per_question_type"] = {}
            for qtype, indices in sorted(question_type_groups.items()):
                stats["per_question_type"][qtype] = {"count": len(indices)}
                for metric in metric_names:
                    values = []
                    for i in indices:
                        m = final_results[i].get("metrics", {}).get(metric, {})
                        if isinstance(m, dict) and "value" in m:
                            values.append(m["value"])
                    if values:
                        stats["per_question_type"][qtype][metric] = sum(values) / len(values)

        stats["total_questions"] = len(final_results)
        stats["model"] = cfg.qa_model

        # Derive user_id, baseline, and ROOT from search_results_path.
        # Path pattern: $ROOT/output/{baseline}/shared/{user_id}/{top_k}_0_1.json
        search_dir = os.path.dirname(cfg.search_results_path)
        user_id = os.path.basename(search_dir)
        baseline = os.path.basename(os.path.dirname(os.path.dirname(search_dir)))
        root_dir = os.path.abspath(os.path.join(search_dir, "..", "..", "..", ".."))
        model_safe = cfg.qa_model.replace("/", "-").replace(".", "-")

        stat_subdir = cfg.stat_output_dir or "res"
        stat_dir = os.path.join(root_dir, stat_subdir, user_id)
        os.makedirs(stat_dir, exist_ok=True)
        stat_path = os.path.join(
            stat_dir,
            f"{user_id}_{model_safe}_{baseline}_evaluation_statistics.json",
        )
        with open(stat_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
        print(f"📊 Evaluation statistics saved to {stat_path}.")

        return final_results
