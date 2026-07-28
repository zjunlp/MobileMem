import json
import re
from string import Template
from typing import Any, Callable

from ..inference_utils.operators import MultimodalQuestionAnsweringOperator
from ..model_types.memory import MemoryEntry
from ..utils.visual_memory import VisualMemoryConfig
from .evaluation import (
    default_context_builder,
    normalize_context_and_images,
    _find_visual_memory_images,
    _truncate_context,
)


def answer_long_context_questions(
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
    multi_qa_batch_size: int = 20,
    debug: bool = False,
) -> list[dict[str, Any]]:
    """Answer questions with multi-question batching for long-context baselines.

    Groups multiple questions into a single LLM call with a shared context.
    The model must output a JSON array of ``{"index": …, "answer": …}``
    objects. On parse failure the batch size is automatically reduced by 5
    (minimum 5) and retried.

    Args:
        Same as :func:`answer_questions` in ``evaluation.py``.
        multi_qa_batch_size: Number of questions per batch (default 20).
        debug: If True, print full raw response on parse failure.
    """
    import time as _time
    import os as _os

    interface_kwargs = interface_kwargs or {}
    visual_memory_config = visual_memory_config or VisualMemoryConfig()

    # Load image caption map and collect unique captions.
    try:
        with open("data/image_to_caption_map.json", encoding="utf-8") as _f:
            _caption_map = json.load(_f)
    except Exception:
        _caption_map = {}
    _captions_text = ""
    if _caption_map and retrievals:
        _seen = set()
        caps = []
        # All items share the same memories in long_context; use first.
        for mem in retrievals[0]["retrieved_memories"]:
            paths = [mem.image_path] if isinstance(mem.image_path, str) else (mem.image_path or [])
            for p in paths:
                basename = _os.path.basename(p)
                if basename not in _seen:
                    _seen.add(basename)
                    cap = _caption_map.get(basename)
                    if cap:
                        caps.append(cap)
        if caps:
            _captions_text = "\n\nImage Captions:\n" + "\n".join(
                f"--- caption {i+1} ---\n{c}" for i, c in enumerate(caps)
            )

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
                device=visual_memory_config.device,
            )
        elif visual_memory_config.retriever_type == "internvideo2":
            from ..utils.internvideo2_search import InternVideo2Searcher

            visual_memory_searcher = InternVideo2Searcher(
                model_id=visual_memory_config.model_id,
                batch_size=visual_memory_config.batch_size,
                device=visual_memory_config.device,
                trust_remote_code=visual_memory_config.trust_remote_code,
            )

    questions = []
    contexts = []
    images = []

    # Build shared context once (all items share the same memory).
    qa_operator = MultimodalQuestionAnsweringOperator(
        prompt_name="structured-question-answering",
        model_name=qa_model,
        timeout=120.0,
        **interface_kwargs,
    )
    if prompt_template is not None:
        qa_operator.set_prompt(prompt_template())

    if retrievals:
        shared_memories = retrievals[0]["retrieved_memories"]
        context, image = normalize_context_and_images(
            context_builder(shared_memories)
        )

        if _captions_text:
            context += _captions_text

        recall_start = len(image)

        if visual_memory_searcher is not None and visual_memory_config.enabled:
            visual_context, visual_images = _find_visual_memory_images(
                uid,
                retrievals[0]["qa_pair"].question,
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

        if "qwen" in qa_model.lower():
            qwen_budget = max_total_tokens or max_context_tokens
            if qwen_budget is not None:
                from ..utils.qwen_vl_utils import truncate_qwen, _load_processor
                qwen_processor = _load_processor("Qwen/Qwen3-VL-8B-Instruct")
                context, image = truncate_qwen(
                    question=retrievals[0]["qa_pair"].question,
                    context=context,
                    image_paths=image,
                    processor=qwen_processor,
                    max_total_tokens=qwen_budget,
                    reserve_for_output=reserve_for_output,
                    no_image=not include_image,
                    prompt_template=qa_operator.prompt,
                )
        elif max_context_tokens is not None:
            context = _truncate_context(context, max_context_tokens, qa_model)

    # Format questions and reuse shared context for all items.
    total_retrievals = len(retrievals)
    for i, item in enumerate(retrievals):
        if debug and (i % 10 == 0 or i == total_retrievals - 1):
            print(f"[Progress] Formatting question {i + 1}/{total_retrievals}...")

        qa_pair = item["qa_pair"]
        question = qa_pair.question
        if "name" in qa_pair.metadata:
            question = f"{qa_pair.metadata['name']}: {question}"
        if add_question_timestamp:
            question += f"\nQuestion Timestamp:{qa_pair.timestamp}"
        question = f"[{qa_pair.question_format}] " + question
        questions.append(question)
        contexts.append(context)
        images.append(image)

    if debug:
        print(f"[Progress] Done ({total_retrievals} items).")

    # ── Batched answering with retry ──
    responses: list[dict[str, Any]] = []
    idx = 0
    total = len(questions)
    # ── Detect the API client pool size ──
    _pool_size = 1
    if (
        hasattr(qa_operator, "interface")
        and hasattr(qa_operator.interface, "client_pool")
    ):
        _pool_size = len(qa_operator.interface.client_pool)
    if debug:
        print(
            f"[Progress] Starting LLM calls ({total} questions, "
            f"batch size {multi_qa_batch_size}, pool_size={_pool_size})..."
        )

    # ── Helper: build the prompt for a single sub-batch ──
    def _build_sub_messages(sub_qs, batch_ctx, img_base_idx):
        numbered_qs = "\n".join(
            f"Question {i}: {q}" for i, q in enumerate(sub_qs)
        )
        prompt_text = (
            "Below is the conversation history:\n"
            f"{batch_ctx}\n\n"
            f"Answer the following {len(sub_qs)} questions based "
            "on the above conversation history.\n"
            "Output your answers as a JSON array of objects. "
            'Each object must have an "index" field '
            "(the question number) and an \"answer\" field.\n\n"
            f"{numbered_qs}\n\n"
            "Provide your answers in the following JSON format:\n"
            "```json\n"
            "[\n"
            '  {"index": 0, "answer": "..."},\n'
            '  {"index": 1, "answer": "..."}\n'
            "]\n"
            "```"
        )
        if include_image and img_base_idx < len(images) and images[img_base_idx]:
            from ..utils.b64_utils import convert_image_to_base64

            content_parts = [{"type": "text", "text": prompt_text}]
            for ii, img_path in enumerate(images[img_base_idx]):
                if isinstance(img_path, str) and img_path.startswith("data:image"):
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img_path},
                    })
                elif isinstance(img_path, str) and img_path:
                    size = (256, 256) if ii < recall_start else (512, 512)
                    img_base64 = convert_image_to_base64(img_path, size)
                    if img_base64:
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": img_base64},
                        })
            return [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": content_parts},
            ]
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt_text},
        ]

    # ── Helper: parse a single response into {index: answer} ──
    def _parse_response(raw_content, expected_count):
        if not raw_content.strip():
            raise ValueError("empty response (model rejected or timed out)")
        json_match = re.search(
            r"```(?:json)?\s*\n(.*?)```", raw_content, re.DOTALL
        )
        if json_match:
            answers = json.loads(json_match.group(1))
        else:
            answers = json.loads(raw_content)
        if isinstance(answers, dict) and "answers" in answers:
            answers = answers["answers"]
        answer_map = {}
        for a in answers:
            if isinstance(a, dict) and "index" in a:
                answer_map[a["index"]] = str(a.get("answer", ""))
        # Ensure the counts match
        for i in range(expected_count):
            if i not in answer_map:
                answer_map[i] = ""
        return answer_map

    # ── Sub-batch log directory ──
    _sub_log_dir = ""
    if interface_kwargs:
        _debug_dir = interface_kwargs.get("debug_output_dir", "")
        if _debug_dir:
            _sub_log_dir = _os.path.join(
                _os.path.dirname(_debug_dir.rstrip("/\\")), "sub_batch_logs"
            )
            _os.makedirs(_sub_log_dir, exist_ok=True)

    # ── Write a sub-batch log ──
    def _write_sub_log(k, s, e, raw_content, status, detail=""):
        if not _sub_log_dir:
            return
        log_path = _os.path.join(
            _sub_log_dir,
            f"batch_{idx // multi_qa_batch_size}_sub_{k}_"
            f"q{idx + s}-{idx + e - 1}_{status}.log",
        )
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Status: {status}\n")
            f.write(f"Questions: q{idx + s} ~ q{idx + e - 1} ({e - s} total)\n")
            if detail:
                f.write(f"Detail: {detail}\n")
            f.write(f"\n--- Raw Response ---\n{raw_content}\n")

    # ── Main batching loop ──
    while idx < total:
        remaining = total - idx
        curr = min(multi_qa_batch_size, remaining)

        while True:
            batch_qs = questions[idx: idx + curr]
            batch_ctx = contexts[idx]

            # ── Parallel path: split into pool_size sub-batches and send them concurrently ──
            if _pool_size > 1 and curr >= _pool_size:
                n_keys = min(_pool_size, curr)
                sub_size = (curr + n_keys - 1) // n_keys
                all_messages = []
                sub_boundaries = []
                for k in range(n_keys):
                    s = k * sub_size
                    e = min(s + sub_size, curr)
                    if s >= e:
                        break
                    sub_boundaries.append((s, e))
                    all_messages.append(
                        _build_sub_messages(batch_qs[s:e], batch_ctx, idx)
                    )

                if idx == 0:
                    debug_dir = (interface_kwargs or {}).get(
                        "debug_output_dir", "output/message_logs"
                    )
                    save_dir = _os.path.dirname(debug_dir.rstrip("/\\"))
                    qa_operator._save_request_payload(
                        messages_list=all_messages,
                        inference_kwargs={"temperature": 0.0},
                        debug_output_dir=save_dir,
                        request_tag="multi_qa_parallel",
                    )

                batch_label = (
                    f"[Batch {idx // multi_qa_batch_size + 1}/"
                    f"{(total + multi_qa_batch_size - 1) // multi_qa_batch_size}]"
                )
                print(
                    f"{batch_label} Sending {curr} questions "
                    f"split into {len(all_messages)} sub-batches..."
                )
                _t0 = _time.time()
                raw_results = qa_operator.interface(
                    all_messages, temperature=0.0
                )
                if not isinstance(raw_results, list):
                    raw_results = [raw_results]
                _elapsed = _time.time() - _t0
                print(
                    f"{batch_label} All {len(raw_results)} responses "
                    f"received in {_elapsed:.1f}s"
                )

                temp_responses = []
                first_failed = None  # (s, e, k) of first failed sub-batch
                for k, (s, e) in enumerate(sub_boundaries):
                    result = raw_results[k] if k < len(raw_results) else {}
                    raw_content = (result or {}).get("content") or ""
                    try:
                        answer_map = _parse_response(raw_content, e - s)
                        for i in range(e - s):
                            temp_responses.append(
                                {"processed_content": answer_map.get(i, "")}
                            )
                        _write_sub_log(k, s, e, raw_content, "ok")
                    except Exception as ex:
                        _write_sub_log(
                            k, s, e, raw_content, "parse_failed", str(ex)
                        )
                        print(
                            f"  [WARNING] Sub-batch {k} parse failed "
                            f"({e - s} questions, see {_sub_log_dir})"
                        )
                        first_failed = (s, e, k)
                        break

                if first_failed is None:
                    responses.extend(temp_responses)
                    idx += curr
                    break
                # ── Partial success: keep successful sub-batches and retry failed and subsequent ones ──
                responses.extend(temp_responses)
                idx += first_failed[0]  # advance past successfully parsed questions
                remain = curr - first_failed[0]
                print(f"  Retrying remaining {remain} questions (failed sub-batch {first_failed[2]})...")
                curr = remain
                continue
            else:
                # ── Sequential path: preserve the original behavior ──
                messages = _build_sub_messages(batch_qs, batch_ctx, idx)

                if idx == 0:
                    debug_dir = (interface_kwargs or {}).get(
                        "debug_output_dir", "output/message_logs"
                    )
                    save_dir = _os.path.dirname(debug_dir.rstrip("/\\"))
                    qa_operator._save_request_payload(
                        messages_list=[messages],
                        inference_kwargs={"temperature": 0.0},
                        debug_output_dir=save_dir,
                        request_tag="multi_qa",
                    )

                batch_label = (
                    f"[Batch {idx // multi_qa_batch_size + 1}/"
                    f"{(total + multi_qa_batch_size - 1) // multi_qa_batch_size}]"
                )
                if debug:
                    print(
                        f"{batch_label} Sending {curr} questions "
                        f"(idx {idx}-{idx + curr - 1})..."
                    )
                _t0 = _time.time()
                result = qa_operator.interface([messages], temperature=0.0)
                if isinstance(result, list):
                    result = result[0]
                if debug:
                    _elapsed = _time.time() - _t0
                    print(f"{batch_label} Response received in {_elapsed:.1f}s")

                raw_content = (result or {}).get("content") or ""
                if debug:
                    print(
                        f"[Response for idx {idx}-{idx + curr - 1}]:\n"
                        f"{raw_content}\n"
                    )

                try:
                    answer_map = _parse_response(raw_content, curr)
                    for i in range(curr):
                        responses.append(
                            {"processed_content": answer_map.get(i, "")}
                        )
                    idx += curr
                    break
                except Exception as e:
                    print(
                        f"[WARNING] Failed to parse multi-qa response "
                        f"(batch size {curr} at idx {idx}): {e}"
                    )

            # ── Shared retry logic ──
            if curr <= 5:
                print(f"  Already at minimum ({curr}), giving up.")
                for _ in range(curr):
                    responses.append({"processed_content": ""})
                idx += curr
                break
            else:
                curr = max(curr - 5, 5)
                print(f"  Retrying with batch size {curr}...")

    return responses
