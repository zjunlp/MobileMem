import re
import json
import math
import threading
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from queue import Queue
from typing import Any, TypedDict
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .llm_judge import LLMJudge
from .retrieval_cache import RetrievalCache, build_retrieval_record

CATEGORIES = {
    1: "Multi-hop",
    2: "Temporal Reasoning",
    3: "Abstention",
    4: "Single-hop",
    5: "Implicit Preference",
    6: "Visual Reasoning",
    7: "Knowledge Update",
}

class Summary(TypedDict):
    total_questions: int
    overall: dict[str, float]
    by_category: dict[str, Any]


class Evaluator:
    """
    Evaluates model performance on conversation-based QA tasks using
    F1, BLEU, and LLM-based judging.
    """

    def __init__(
        self,
        methods: list,
        judge: LLMJudge,
        database_root_path: str
    ):
        self.judge = judge
        self.database_root_path = database_root_path
        self.method_pool = Queue()
        for m in methods:
            self.method_pool.put(m)
        self.stats_lock = threading.Lock()

    # --- Metric Calculations ---

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Tokenizes string into lowercase words and CJK characters."""
        text = str(text).lower()
        text = re.sub(r'[\u0000-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E]', ' ', text)
        return re.findall(r'[\u4e00-\u9fff]|[a-z0-9]+', text)

    def calculate_f1(self, pred: str, ref: str) -> float:
        pt, rt = self.tokenize(pred), self.tokenize(ref)
        if not pt and not rt: return 1.0
        if not pt or not rt: return 0.0
        pc, rc = Counter(pt), Counter(rt)
        overlap = sum((pc & rc).values())
        if overlap == 0: return 0.0
        precision = overlap / len(pt)
        recall = overlap / len(rt)
        return 2 * precision * recall / (precision + recall)

    def calculate_bleu1(self, pred: str, ref: str) -> float:
        pt, rt = self.tokenize(pred), self.tokenize(ref)
        if not pt: return 0.0
        pc, rc = Counter(pt), Counter(rt)
        clipped_overlap = sum(min(pc[w], rc[w]) for w in pc)
        precision = clipped_overlap / len(pt)
        bp = math.exp(1 - len(rt) / len(pt)) if len(pt) < len(rt) else 1.0
        return bp * precision

    def _get_best_metrics(self, pred: str, refs: list[str]) -> tuple[float, float, str]:
        best_f1, best_bleu, best_ref = -1, -1, ""
        for r in refs:
            f1 = self.calculate_f1(pred, r)
            bleu = self.calculate_bleu1(pred, r)
            if (f1 + bleu) > (best_f1 + best_bleu):
                best_f1, best_bleu, best_ref = f1, bleu, r
        return best_f1, best_bleu, best_ref

    # --- Data Normalization ---

    def _norm_imgs(self, imgs: Any) -> list:
        if imgs is None: return []
        return [imgs] if isinstance(imgs, (str, dict)) else list(imgs)

    def _norm_refs(self, refs: Any) -> list[str]:
        if refs is None: return [""]
        if isinstance(refs, (str, int, float, bool)): return [str(refs)]
        items = [refs] if isinstance(refs, dict) else refs
        out = []
        for x in items:
            if isinstance(x, dict):
                val = x.get("text") or x.get("answer") or x.get("value") or ""
                out.append(str(val))
            else:
                out.append(str(x))
        return out or [""]

    def _is_multiple_choice_qa(self, qa: dict) -> bool:
        question_format = str(qa.get("question_format") or "").strip().lower()
        if question_format == "multiple_choice":
            return True
        question = str(qa.get("question") or "")
        return bool(re.search(r"(?m)^A[.．、]\s+.+\nB[.．、]\s+", question))

    def _filter_local_results(self, local_results: dict, keep_qids: set[str]) -> dict:
        filtered = {}
        for category, items in (local_results or {}).items():
            kept = [item for item in items if item.get("id") in keep_qids]
            if kept:
                filtered[category] = kept
        return filtered

    def _relabel_local_results(self, local_results: dict, qas: list[dict]) -> dict:
        category_by_qid = {
            qa["qid"]: CATEGORIES.get(qa["category"], str(qa["category"]))
            for qa in qas
        }
        relabeled = {}
        for old_category, items in (local_results or {}).items():
            for item in items:
                category = category_by_qid.get(item.get("id"), old_category)
                relabeled.setdefault(category, []).append(item)
        return relabeled

    # --- Data Collection ---

    def _build_dialogue(self, conversation: dict) -> list[dict]:
        """Flattens session-based conversation into a chronological list."""
        dialogue = []
        idx = 0
        while True:
            key = f"session_{idx}"
            if key not in conversation:
                break
            utterances = conversation[key]
            if isinstance(utterances, list):
                timestamp = conversation.get(f"session_{idx}_date_time", "")
                for u in utterances:
                    dialogue.append({
                        "speaker": u["speaker"],
                        "dia_id": u.get("dia_id", ""),
                        "images": self._norm_imgs(u.get("images", [])),
                        "text": u.get("text", ""),
                        "image_caption": u.get("image_caption", ""),
                        "timestamp": timestamp,
                        "session_idx": idx,
                    })
            idx += 1
        return dialogue

    def _collect_conversations(self, data: list[dict]) -> list[dict]:
        processed = []
        for i, item in enumerate(data):
            source_idx = item.get("_m2a_original_index", i)
            qas = []
            for j, qa in enumerate(item.get("qa", [])):
                q = qa["question"]
                qas.append({
                    "qid": f"{source_idx}:{j}",
                    "question": q["text"],
                    "images": self._norm_imgs(q.get("image", [])),
                    "refs": self._norm_refs(qa.get("answers") or qa.get("answer")),
                    "category": qa.get("category", "default"),
                    "question_format": qa.get("question_format"),
                    "evidence": qa.get("evidence", []),
                })
            processed.append({
                "cid": source_idx,
                "dialogue": self._build_dialogue(item["conversation"]),
                "qas": qas,
                "fast_memories": item.get("fast_memories", []),
                "conv_info": {
                    "speaker_0": item['conversation'].get("speaker_0"),
                    "speaker_1": item['conversation'].get("speaker_1")
                }
            })
        return processed

    # --- Summary Calculation ---

    def calc_summary(self, results: dict, done: int) -> dict:
        """Aggregates metrics into a structured summary."""
        all_items = [x for items in results.values() for x in items]
        judged_items = [x for x in all_items if x['judge_label'] is not None]

        overall = {
            "F1": sum(x['f1'] for x in all_items) / len(all_items) if all_items else 0.0,
            "BLEU1": sum(x['bleu1'] for x in all_items) / len(all_items) if all_items else 0.0,
            "LLM_JUDGE": (
                sum(x['judge_label'] == "CORRECT" for x in judged_items) / len(judged_items)
                if judged_items else 0.0
            )
        }

        by_category = {}
        for cat, items in results.items():
            cat_judged = [x for x in items if x['judge_label'] is not None]
            by_category[cat] = {
                "count": len(items),
                "metrics": {
                    "F1": sum(x['f1'] for x in items) / len(items),
                    "BLEU1": sum(x['bleu1'] for x in items) / len(items),
                    "LLM_JUDGE": (
                        sum(x['judge_label'] == "CORRECT" for x in cat_judged) / len(cat_judged)
                        if cat_judged else 0.0
                    ),
                }
            }

        summary_obj: Summary = {
            "total_questions": done,
            "overall": overall,
            "by_category": by_category
        }
        return {"results": results, "summary": summary_obj}

    # --- Execution Logic ---

    def _get_conv_dir(self, method, conv_idx: int) -> Path:
        db_dir = getattr(method, "db_dir", None)
        if db_dir is None:
            return Path("eval_results").joinpath(str(conv_idx))
        return Path(db_dir).joinpath(str(conv_idx))

    def _load_checkpoint(self, conv_dir: Path) -> dict:
        ckpt_path = conv_dir.joinpath("checkpoint.json")
        if not ckpt_path.exists():
            return {}
        try:
            return json.loads(ckpt_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_checkpoint(
        self,
        conv_dir: Path,
        conv_idx: int,
        phase: str,
        chat_done: int,
        chat_total: int,
        qa_done_ids: set[str],
        qa_total: int,
        local_results: dict,
        method=None,
    ) -> None:
        conv_dir.mkdir(parents=True, exist_ok=True)
        ckpt = {
            "conversation_id": conv_idx,
            "phase": phase,
            "chat_done": chat_done,
            "chat_total": chat_total,
            "qa_done": len(qa_done_ids),
            "qa_total": qa_total,
            "qa_done_ids": sorted(qa_done_ids),
            "results": local_results,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        cur_time = getattr(method, "cur_time", None)
        if cur_time is not None:
            ckpt["cur_time"] = cur_time.isoformat()
        tmp_path = conv_dir.joinpath("checkpoint.json.tmp")
        ckpt_path = conv_dir.joinpath("checkpoint.json")
        tmp_path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(ckpt_path)
        image_manager = getattr(getattr(method, "m2a", None), "image_manager", None)
        if image_manager is not None:
            try:
                image_manager.save(str(conv_dir.joinpath("image_manager_checkpoint.json")))
            except Exception as exc:
                print(f"Warning: failed to save image manager checkpoint for conv {conv_idx}: {ascii(str(exc))}")

    def _load_final_results(self, conv_dir: Path) -> dict | None:
        results_path = conv_dir.joinpath("results.json")
        if not results_path.exists():
            return None
        try:
            return json.loads(results_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _worker(
        self,
        conv_idx,
        conv,
        max_samples,
        n_sample_msg,
        resume=False,
        checkpoint_every_chat=10,
        checkpoint_every_qa=1,
        memory_build_mode="agent",
        semantic_batch_size=64,
        embed_image_memories=False,
        image_embedding_batch_size=4,
        index_caption_memories=False,
        caption_chunk_chars=800,
        caption_chunk_overlap=80,
        run_stage="all",
        skip_multiple_choice=False,
        save_retrieval_cache=False,
        retrieval_cache_dir=None,
    ):
        method = self.method_pool.get()
        try:
            if run_stage not in {"all", "build", "qa", "retrieval", "replay"}:
                raise ValueError(f"Unsupported run_stage: {run_stage}")
            retrieval_only = run_stage == "retrieval"
            if retrieval_only:
                save_retrieval_cache = True

            conv_dir = self._get_conv_dir(method, conv_idx)
            if resume:
                final_results = self._load_final_results(conv_dir)
                if (
                    final_results is not None
                    and conv_dir.joinpath("summary.json").exists()
                    and not save_retrieval_cache
                ):
                    print(f"[conv: {conv_idx}] resume skip completed")
                    return conv_idx, final_results

            checkpoint = self._load_checkpoint(conv_dir) if resume else {}
            conv["conv_info"]["conv_idx"] = conv_idx
            dialogue = conv["dialogue"][:n_sample_msg]
            qas = conv["qas"]
            if skip_multiple_choice:
                before_count = len(qas)
                qas = [qa for qa in qas if not self._is_multiple_choice_qa(qa)]
                skipped_count = before_count - len(qas)
                if skipped_count:
                    print(f"[conv: {conv_idx}] skip multiple_choice QA: {skipped_count}/{before_count}")
            qas = qas[:max_samples] if max_samples else qas
            active_qids = {qa["qid"] for qa in qas}
            replay_from_cache = run_stage == "replay"
            if replay_from_cache and not retrieval_cache_dir:
                raise ValueError("Replay mode requires retrieval_cache_dir")
            cache_root = Path(retrieval_cache_dir) if retrieval_cache_dir else conv_dir.parent
            cache_path = cache_root.joinpath(str(conv_idx), "retrieval_cache.jsonl")
            retrieval_cache = None
            if save_retrieval_cache or replay_from_cache:
                retrieval_cache = RetrievalCache(
                    cache_path,
                    reset=save_retrieval_cache and not resume,
                )
            if replay_from_cache:
                for qa in qas:
                    retrieval_cache.require(qa["qid"], qa["question"], qa.get("images", []))

            chat_done = min(int(checkpoint.get("chat_done", 0) or 0), len(dialogue))
            local_results = checkpoint.get("results", {}) if resume else {}
            if resume and local_results:
                local_results = self._relabel_local_results(local_results, qas)
            qa_done_ids = set(checkpoint.get("qa_done_ids", [])) if resume else set()
            if skip_multiple_choice:
                local_results = self._filter_local_results(local_results, active_qids)
                qa_done_ids &= active_qids
            if save_retrieval_cache and not retrieval_only:
                cached_qids = set()
                for qa in qas:
                    if qa["qid"] in retrieval_cache.records:
                        retrieval_cache.require(
                            qa["qid"], qa["question"], qa.get("images", [])
                        )
                        cached_qids.add(qa["qid"])
                qa_done_ids &= cached_qids
                local_results = self._filter_local_results(local_results, qa_done_ids)
            store_exists = conv_dir.joinpath("raw.db").exists() and conv_dir.joinpath("semantic.db").exists()

            if run_stage == "build" and resume and chat_done >= len(dialogue) and store_exists:
                print(f"[conv: {conv_idx}] resume skip built memory")
                return conv_idx, {}

            if run_stage in {"qa", "retrieval"} and not (
                resume and chat_done >= len(dialogue) and store_exists
            ):
                raise RuntimeError(
                    f"{run_stage} requires an existing completed build for conv {conv_idx}. "
                    f"Expected checkpoint chat_done={len(dialogue)} and existing raw.db/semantic.db in {conv_dir}."
                )

            if replay_from_cache:
                method.start_replay_conversation(conv_info=conv["conv_info"])
                chat_done = len(dialogue)
            else:
                should_resume_store = resume and bool(checkpoint) and (
                    conv_dir.joinpath("raw.db").exists() or conv_dir.joinpath("semantic.db").exists()
                ) and (memory_build_mode == "agent" or chat_done >= len(dialogue))
                method.start_conversation(conv_info=conv["conv_info"], resume=should_resume_store)
                if chat_done > 0 and getattr(method, "cur_time", None) is None and dialogue:
                    method.cur_time = method._format_time(dialogue[chat_done - 1]["timestamp"])

            def chat_checkpoint(done: int, wrapper) -> None:
                if checkpoint_every_chat > 0 and (done % checkpoint_every_chat == 0 or done == len(dialogue)):
                    self._save_checkpoint(
                        conv_dir,
                        conv_idx,
                        "chat",
                        done,
                        len(dialogue),
                        qa_done_ids,
                        len(qas),
                        local_results,
                        wrapper,
                    )

            if not replay_from_cache and chat_done < len(dialogue):
                if memory_build_mode == "agent":
                    method.chat(dialogue, start_index=chat_done, checkpoint_callback=chat_checkpoint)
                else:
                    method.fast_build_memory(
                        dialogue,
                        fast_memories=conv.get("fast_memories", []),
                        build_mode=memory_build_mode,
                        semantic_batch_size=semantic_batch_size,
                        embed_image_memories=embed_image_memories,
                        image_embedding_batch_size=image_embedding_batch_size,
                        index_caption_memories=index_caption_memories,
                        caption_chunk_chars=caption_chunk_chars,
                        caption_chunk_overlap=caption_chunk_overlap,
                    )
                chat_done = len(dialogue)
                self._save_checkpoint(
                    conv_dir, conv_idx, "chat_done", chat_done, len(dialogue),
                    qa_done_ids, len(qas), local_results, method
                )

            if run_stage == "build":
                return conv_idx, {}

            if chat_done >= len(dialogue) and checkpoint.get("phase") == "chat_done":
                qa_done_ids = set(checkpoint.get("qa_done_ids", []))

            for qa in tqdm(qas, desc=f"[conv: {conv_idx}] Test"):
                if retrieval_only and qa["qid"] in retrieval_cache.records:
                    retrieval_cache.require(
                        qa["qid"], qa["question"], qa.get("images", [])
                    )
                    continue
                if not retrieval_only and qa["qid"] in qa_done_ids:
                    continue
                try:
                    if replay_from_cache:
                        cache_record = retrieval_cache.require(
                            qa["qid"], qa["question"], qa.get("images", [])
                        )
                        pred = method.question_from_retrieval_cache(qa["question"], cache_record)
                    elif save_retrieval_cache and qa["qid"] in retrieval_cache.records:
                        cache_record = retrieval_cache.require(
                            qa["qid"], qa["question"], qa.get("images", [])
                        )
                        pred = method.question_from_retrieval_cache(qa["question"], cache_record)
                    else:
                        pred = method.question(qa["question"], qa.get("images", []))
                        cache_record = None
                        if save_retrieval_cache:
                            cache_record = build_retrieval_record(
                                conversation_id=conv_idx,
                                question_id=qa["qid"],
                                question=qa["question"],
                                images=qa.get("images", []),
                                retrieval_trace=method.get_last_retrieval_trace(),
                                retrieval_model=method.config.llm.model,
                                current_time=getattr(method, "cur_time", None),
                            )
                            retrieval_cache.append(cache_record)
                        if retrieval_only:
                            continue
                    f1, bleu, ref_used = self._get_best_metrics(pred, qa["refs"])

                    judge_label, judge_rationale = None, None
                    if self.judge and ref_used:
                        j = self.judge.score(
                            qa["question"],
                            ref_used,
                            pred,
                            images=qa.get("images", []),
                            evidence=qa.get("evidence", []),
                        )
                        judge_label, judge_rationale = j.get("label"), j.get("rationale")

                    cat_name = CATEGORIES.get(qa['category'], str(qa['category']))
                    raw_entry = {
                        "id": qa["qid"], "conversation_id": conv["cid"],
                        "question": qa["question"], "prediction": pred,
                        "reference_used": ref_used, "f1": f1, "bleu1": bleu,
                        "evidence": qa.get("evidence", []),
                        "judge_label": judge_label, "judge_rationale": judge_rationale,
                        "retrieval_cache": {
                            "mode": "replay" if replay_from_cache else "record" if save_retrieval_cache else "off",
                            "question_fingerprint": (
                                cache_record.get("question_fingerprint") if cache_record else None
                            ),
                            "source": str(cache_path) if cache_record else None,
                        },
                    }
                    local_results.setdefault(cat_name, []).append(raw_entry)
                    qa_done_ids.add(qa["qid"])
                    if checkpoint_every_qa > 0 and (len(qa_done_ids) % checkpoint_every_qa == 0 or len(qa_done_ids) == len(qas)):
                        self._save_checkpoint(
                            conv_dir,
                            conv_idx,
                            "qa",
                            chat_done,
                            len(dialogue),
                            qa_done_ids,
                            len(qas),
                            local_results,
                            method,
                        )
                except Exception as e:
                    print(f"Error in conversation {conv_idx}: {ascii(str(e))}")
                    if replay_from_cache or save_retrieval_cache:
                        raise

            if retrieval_cache is not None:
                retrieval_models = sorted({
                    str(record.get("retrieval_model"))
                    for qid, record in retrieval_cache.records.items()
                    if qid in active_qids and record.get("retrieval_model")
                })
                manifest = {
                    "schema_version": 1,
                    "conversation_id": conv_idx,
                    "mode": (
                        "replay" if replay_from_cache
                        else "retrieval" if retrieval_only
                        else "record"
                    ),
                    "cache_path": str(cache_path.resolve()),
                    "cached_questions": len(retrieval_cache),
                    "required_questions": len(qas),
                    "complete": all(qid in retrieval_cache.records for qid in active_qids),
                    "retrieval_models": retrieval_models,
                    "answer_model": None if retrieval_only else method.config.llm.model,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                manifest_path = (
                    conv_dir.joinpath("retrieval_replay_manifest.json")
                    if replay_from_cache
                    else cache_path.parent.joinpath("retrieval_cache_manifest.json")
                )
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            if retrieval_only:
                return conv_idx, {}

            done = sum(len(v) for v in local_results.values())
            conv_summary = self.calc_summary(local_results, done)
            method.over(**conv_summary)
            self._save_checkpoint(
                conv_dir,
                conv_idx,
                "done",
                chat_done,
                len(dialogue),
                qa_done_ids,
                len(qas),
                local_results,
                method,
            )

            return conv_idx, local_results
        except Exception as e:
            print(f"Error in conversation {conv_idx}: {ascii(str(e))}")
            if run_stage in {"retrieval", "replay"} or save_retrieval_cache:
                raise
            return conv_idx, {}
        finally:
            close_conversation = getattr(method, "close_conversation", None)
            if callable(close_conversation):
                try:
                    close_conversation()
                except Exception as exc:
                    print(f"Warning: failed to close conversation {conv_idx}: {ascii(str(exc))}")
            self.method_pool.put(method)

    def evaluate(
        self,
        conversations,
        max_samples=None,
        n_sample_conv=100,
        n_sample_msg=10000,
        resume=False,
        checkpoint_every_chat=10,
        checkpoint_every_qa=1,
        conv_start=0,
        conv_end=None,
        memory_build_mode="agent",
        semantic_batch_size=64,
        embed_image_memories=False,
        image_embedding_batch_size=4,
        index_caption_memories=False,
        caption_chunk_chars=800,
        caption_chunk_overlap=80,
        run_stage="all",
        skip_multiple_choice=False,
        save_retrieval_cache=False,
        retrieval_cache_dir=None,
    ):
        all_conv_results = {}
        num_workers = self.method_pool.qsize()
        all_targets = [
            (conv.get("cid", i), conv)
            for i, conv in enumerate(conversations)
        ]
        if conv_end is None:
            conv_end = len(all_targets)
        if n_sample_conv is not None:
            conv_end = min(conv_end, conv_start + n_sample_conv)
        targets = all_targets[conv_start:conv_end]

        executor = ThreadPoolExecutor(max_workers=num_workers)
        futures = [
                executor.submit(
                    self._worker,
                    i,
                    conv,
                    max_samples,
                    n_sample_msg,
                    resume,
                    checkpoint_every_chat,
                    checkpoint_every_qa,
                    memory_build_mode,
                    semantic_batch_size,
                    embed_image_memories,
                    image_embedding_batch_size,
                    index_caption_memories,
                    caption_chunk_chars,
                    caption_chunk_overlap,
                    run_stage,
                    skip_multiple_choice,
                    save_retrieval_cache,
                    retrieval_cache_dir,
                )
                for i, conv in targets
        ]
        try:
            for future in tqdm(as_completed(futures), total=len(futures), desc="Total Progress"):
                item = future.result()
                if item is None:
                    continue
                idx, res = item
                all_conv_results[idx] = res
        except BaseException:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

        return self._aggregate_and_print(all_conv_results)

    def _aggregate_and_print(self, all_conv_results: dict) -> dict:
        merged_results = {}
        for local_results in all_conv_results.values():
            for cat, items in local_results.items():
                merged_results.setdefault(cat, []).extend(items)

        total_done = sum(len(items) for items in merged_results.values())
        final_data = self.calc_summary(merged_results, total_done)
        self.print_summary(final_data['summary'])
        return final_data

    def print_summary(self, summary: Summary) -> None:
        line = "=" * 60
        print(f"\n{line}\n EVALUATION SUMMARY \n{line}")
        print("Overall:")
        for metric, score in summary['overall'].items():
            print(f"  {metric:10s}: {score:.4f}")
        print("\nBy Category:")
        for cat, data in summary['by_category'].items():
            print(f"  {cat} (n={data['count']}):")
            for metric, score in data['metrics'].items():
                print(f"    {metric}: {score:.4f}")
        print(f"{line}\n")

    def evaluate_file(self, path, **kwargs):
        full_path = f"{self.database_root_path}/{path}"
        with open(full_path, "r", encoding="utf-8") as f:
            data = [json.loads(line) for line in f] if path.endswith(".jsonl") else json.load(f)
        conversations = self._collect_conversations(data)
        return self.evaluate(conversations, **kwargs)
