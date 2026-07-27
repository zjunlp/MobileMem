#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 stage5.json + stage6.json 的标准合并格式，
为每个用户生成 data/Locomo/locomo_u{x}.json 文件，
兼容 membase/datasets/locomo.py 的读取格式。
"""

import json
import os
import sys
import argparse
import copy
from pathlib import Path
from datetime import datetime

# ============ 图片路径工具 ============

def normalize_image_path(image_path: str) -> str:
    if not image_path:
        return ""
    if image_path.startswith("[image:") and image_path.endswith("]"):
        image_path = image_path[7:-1]
    image_path = image_path.replace("\\", "/")
    filename = os.path.basename(image_path)
    if not filename:
        parts = image_path.split("/")
        filename = parts[-1] if parts else ""
    return filename.strip()


def clean_filename(image_path_value: str) -> str:
    if image_path_value.startswith("[image:") and image_path_value.endswith("]"):
        return image_path_value[7:-1]
    return image_path_value


# ============ 时间戳转换 ============

def parse_stage5_timestamp(ts_str: str) -> datetime | None:
    """解析 stage5 中的时间戳字符串 '2025-01-01 09:00:00'"""
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_locomo_date(dt: datetime) -> str:
    """格式化为 '1:56 pm on 8 May, 2023'"""
    if dt is None:
        return ""
    hour = dt.strftime("%I").lstrip("0")
    minute = dt.strftime("%M")
    am_pm = dt.strftime("%p").lower()
    day = dt.day
    month = dt.strftime("%b")
    year = dt.year
    return f"{hour}:{minute} {am_pm} on {day} {month}, {year}"


# ============ 图片摘要加载 ============

def load_image_summaries(path: str) -> dict[str, str]:
    """加载 stage10_image_summaries.jsonl，返回 filename -> summary_zh/en 映射"""
    summary_map = {}
    if not os.path.exists(path):
        print(f"警告: 图片摘要文件不存在: {path}")
        return summary_map
    with open(path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line.strip())
            filename = record.get("filename", "")
            if not filename:
                continue
            summary_zh = record.get("summary_zh", "")
            summary_en = record.get("summary_en", "")
            summary_map[filename] = summary_zh if summary_zh else summary_en
    print(f"  加载了 {len(summary_map)} 条图片摘要")
    return summary_map


# ============ 问题类型映射 ============

QUESTION_TYPE_TO_CATEGORY = {
    "single_hop": 4,
    "multi_hop": 1,
    "temporal_reasoning": 2,
    "implicit_preference": 5,
    "visual_reasoning": 6,
    "multi_visual_reasoning": 6,
    "abstention": 3,
    "knowledge_update": 7,
}


# ============ 核心转换 ============

def convert_session(session: dict, session_index: int, image_summary_map: dict, no_caption_in_text: bool = False) -> tuple[list[dict], str]:
    """将 stage5 的一个 session 转换为 locomo session 格式"""
    session_id = session.get("session_id", "")
    event_start_time = session.get("event_start_time", "")
    dt = parse_stage5_timestamp(event_start_time)

    turns = []
    dialogue = session.get("dialogue", [])
    for i, turn in enumerate(dialogue, 1):
        role = turn.get("role", "")
        content = turn.get("content", "")
        image_inline = turn.get("image_inline")

        turn_item = {
            "dia_id": f"D{session_index}:{i}",
            "text": content,
        }

        # 图片处理
        if image_inline:
            # image_inline 可能是字符串或数组
            if isinstance(image_inline, str):
                img_list = [image_inline]
            elif isinstance(image_inline, list):
                img_list = image_inline
            else:
                img_list = []

            # 清理路径并添加 data/ 前缀
            clean_paths = []
            for p in img_list:
                if isinstance(p, str) and p.strip():
                    cleaned = clean_filename(p.strip())
                    if not cleaned.startswith("data/"):
                        cleaned = "data/" + cleaned
                    clean_paths.append(cleaned)
            turn_item["image_path"] = clean_paths if clean_paths else None

            # 从 stage10 匹配 caption 并加入 text
            caption = None
            for p in (clean_paths or []):
                lookup_key = normalize_image_path(p)
                if lookup_key in image_summary_map:
                    caption = image_summary_map[lookup_key]
                    break
            if caption and not no_caption_in_text:
                turn_item["text"] += f"\nImage Caption: {caption}"

        # 处理 speaker
        if role == "user":
            turn_item["speaker"] = None  # 稍后填充
        elif role == "assistant":
            turn_item["speaker"] = None  # 稍后填充
        else:
            turn_item["speaker"] = role

        turns.append(turn_item)

    date_str = format_locomo_date(dt) if dt else ""
    return turns, date_str


def convert_question(q: dict, session_id_to_timestamp: dict) -> dict:
    """将 stage6 的一个 question 转换为 locomo qa 格式"""
    question_text = q.get("question", "")
    options = q.get("options", [])
    if options and isinstance(options, list) and len(options) > 0:
        options_text = "\n".join(options)
        question_text = f"{question_text}\n{options_text}"

    qtype = q.get("question_type", "")
    category = QUESTION_TYPE_TO_CATEGORY.get(qtype, 0)

    # 提取 evidence 文本
    evidence_list = q.get("evidence", [])
    evidence_texts = []
    for ev in evidence_list:
        if isinstance(ev, dict):
            text = ev.get("explanation", "")
            if text:
                evidence_texts.append(text)
        elif isinstance(ev, str):
            evidence_texts.append(ev)

    # 取第一个 source session 的 timestamp
    timestamp = ""
    src_sessions = q.get("source_session_ids", [])
    if src_sessions and isinstance(src_sessions, list):
        for sid in src_sessions:
            if sid in session_id_to_timestamp:
                timestamp = session_id_to_timestamp[sid]
                break

    qa_item = {
        "question": question_text,
        "answer": q.get("answer", ""),
        "evidence": evidence_texts,
        "category": category,
        "timestamp": timestamp,
    }
    question_format = q.get("question_format")
    if question_format:
        qa_item["question_format"] = question_format

    return qa_item


def build_observation_structure(sessions: list, speaker_a: str, speaker_b: str) -> dict:
    observation = {}
    for i, _ in enumerate(sessions, 1):
        observation[f"session_{i}_observation"] = {speaker_a: [], speaker_b: []}
    return observation


def build_event_summary_structure(sessions: list, speaker_a: str, speaker_b: str) -> dict:
    event_summary = {}
    for i, session in enumerate(sessions, 1):
        dt = parse_stage5_timestamp(session.get("event_start_time", ""))
        date_str = f"{dt.day} {dt.strftime('%b, %Y')}" if dt else ""
        event_summary[f"events_session_{i}"] = {
            speaker_a: [],
            speaker_b: [],
            "date": date_str,
        }
    return event_summary


def convert_user(
    stage5_user: dict,
    stage6_user: dict | None,
    image_summary_map: dict,
    no_caption_in_text: bool = False,
) -> dict:
    """将单个用户的 stage5 + stage6 数据转换为 locomo 格式 sample"""
    record = stage5_user["records"][0]
    uuid = record.get("uuid", stage5_user["user_id"])
    persona_name = record.get("Basic_Profile", {}).get("name", f"User{uuid}")
    speaker_b = "助手"

    sessions = record.get("sessions", [])

    # 构建 conversation
    conversation = {"speaker_a": persona_name, "speaker_b": speaker_b}

    # 构建 session_id -> timestamp 映射
    session_id_to_timestamp = {}
    for i, s in enumerate(sessions, 1):
        sid = s.get("session_id", "")
        ts = s.get("event_start_time", "")
        if ts:
            dt = parse_stage5_timestamp(ts)
            if dt:
                session_id_to_timestamp[sid] = dt.isoformat()

    session_summaries = {}
    for i, s in enumerate(sessions, 1):
        sid = s.get("session_id", "")
        session_summaries[f"session_{i}_summary"] = s.get("dialogue_summary", "")

        # 转换对话
        turns, date_str = convert_session(s, i, image_summary_map, no_caption_in_text)

        # 填充 speaker
        for turn in turns:
            if turn.get("speaker") is None:
                # 如果原来的 role 不在 turn 中，需要根据对话判断
                pass

        # 根据 turns 和 role 信息确定 speaker
        dialogue = s.get("dialogue", [])
        for j, turn in enumerate(turns):
            if j < len(dialogue):
                role = dialogue[j].get("role", "user")
                turn["speaker"] = persona_name if role == "user" else speaker_b

        conversation[f"session_{i}_date_time"] = date_str
        conversation[f"session_{i}"] = turns

    # 转换 QA
    qa_list = []
    if stage6_user:
        questions = stage6_user["records"][0].get("questions", [])
        for q in questions:
            qa_item = convert_question(q, session_id_to_timestamp)
            qa_list.append(qa_item)

    # 构建结构化字段
    observation = build_observation_structure(sessions, persona_name, speaker_b)
    event_summary = build_event_summary_structure(sessions, persona_name, speaker_b)

    locomo_sample = {
        "qa": qa_list,
        "conversation": conversation,
        "event_summary": event_summary,
        "observation": observation,
        "session_summary": session_summaries,
        "sample_id": f"uuid_{uuid}",
    }
    return locomo_sample


# ============ 主入口 ============

def main():
    parser = argparse.ArgumentParser(description="将 stage5 + stage6 合并格式转换为 locomo 格式")
    parser.add_argument("--stage5", default="data/Raw/stage5.json", help="stage5 会话数据")
    parser.add_argument("--stage6", default="data/Raw/stage6.json", help="stage6 问答数据")
    parser.add_argument("--stage10", default="data/Raw/stage10_image_summaries.jsonl", help="图片摘要")
    parser.add_argument("--output-dir", default="data/Locomo", help="输出目录")
    parser.add_argument("--users", type=int, nargs="+", default=None, help="指定用户 ID（默认全部）")
    parser.add_argument("--no-image", action="store_true", help="不包含图片字段")
    parser.add_argument("--no-siglip2-index", action="store_true", help="不预生成 SigLIP2 图像索引 .npz 文件")
    parser.add_argument("--no-caption-in-text", action="store_true", help="不将 caption 填入 text 字段")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # 加载数据
    print("=" * 60)
    print("加载 stage5.json ...")
    with open(args.stage5, encoding="utf-8") as f:
        stage5 = json.load(f)
    s5_summary = stage5["summary"]
    print(f"  共 {s5_summary['user_count']} 个用户, {s5_summary['total_sessions']} 个会话")

    print("加载 stage6.json ...")
    with open(args.stage6, encoding="utf-8") as f:
        stage6 = json.load(f)
    s6_summary = stage6["summary"]
    print(f"  共 {s6_summary['user_count']} 个用户, {s6_summary['total_questions']} 个问题")

    print("加载 stage10_image_summaries.jsonl ...")
    image_summary_map = load_image_summaries(args.stage10)

    # ── 生成 image -> event_start_time 映射 ──
    image_to_timestamp: dict[str, str] = {}
    for u_data in stage5["users"]:
        for rec in u_data.get("records", []):
            for sess in rec.get("sessions", []):
                event_ts = sess.get("event_start_time", "")
                if not event_ts:
                    continue
                for turn in sess.get("dialogue", []):
                    image_inline = turn.get("image_inline")
                    if not image_inline:
                        continue
                    if isinstance(image_inline, str):
                        img_list = [image_inline]
                    elif isinstance(image_inline, list):
                        img_list = image_inline
                    else:
                        img_list = []
                    for p in img_list:
                        fn = normalize_image_path(p)
                        if fn and fn not in image_to_timestamp:
                            image_to_timestamp[fn] = event_ts

    ts_map_path = os.path.normpath(os.path.join(args.output_dir, "..", "image_to_timestamp_map.json"))
    with open(ts_map_path, "w", encoding="utf-8") as f:
        json.dump(image_to_timestamp, f, ensure_ascii=False, indent=2)
    print(f"  -> {ts_map_path} ({len(image_to_timestamp)} entries)")

    # ── 生成 image -> caption 映射（来自 stage10） ──
    cap_map_path = os.path.normpath(os.path.join(args.output_dir, "..", "image_to_caption_map.json"))
    with open(cap_map_path, "w", encoding="utf-8") as f:
        json.dump(image_summary_map, f, ensure_ascii=False, indent=2)
    print(f"  -> {cap_map_path} ({len(image_summary_map)} entries)")

    # 构建 stage6 user_id -> user 映射
    stage6_by_uid = {}
    for u in stage6["users"]:
        uid = u["user_id"]
        stage6_by_uid[uid] = u

    # ── 确定要处理的用户 ──
    target_uids = args.users if args.users is not None else s5_summary["user_ids"]
    print(f"\n处理用户: {target_uids}")

    # ── 确保 tmp 目录存在（用于 SigLIP2 索引） ──
    tmp_dir = os.path.normpath(os.path.join(args.output_dir, "..", "tmp"))
    os.makedirs(tmp_dir, exist_ok=True)

    for user_data in stage5["users"]:
        uid = user_data["user_id"]
        if uid not in target_uids:
            continue

        print(f"\n[{uid}] 转换中...")
        s6_data = stage6_by_uid.get(uid)

        locomo_sample = convert_user(user_data, s6_data, image_summary_map, args.no_caption_in_text)

        if args.no_image:
            locomo_sample = remove_visual_fields(locomo_sample)

        output_path = os.path.join(args.output_dir, f"locomo_u{uid}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([locomo_sample], f, ensure_ascii=False, indent=2)

        n_sessions = len(locomo_sample["conversation"]) // 2  # 粗略：减去 speaker_a/speaker_b
        actual_sessions = sum(1 for k in locomo_sample["conversation"] if k.startswith("session_") and not k.endswith("_date_time"))
        print(f"  -> {output_path} ({actual_sessions} 个会话, {len(locomo_sample['qa'])} 个问题)")

        # ── 生成 per-user SigLIP2 图像索引 ──
        if not args.no_image and not args.no_siglip2_index:
            _build_user_siglip2_index(uid, locomo_sample, tmp_dir)

    print(f"\n完成! 输出目录: {args.output_dir}")


def remove_visual_fields(sample: dict) -> dict:
    """递归移除 image_path 和 caption 字段"""
    result = copy.deepcopy(sample)
    conversation = result.get("conversation", {})
    for key, value in conversation.items():
        if key.startswith("session_") and isinstance(value, list):
            for turn in value:
                if isinstance(turn, dict):
                    turn.pop("image_path", None)
                    turn.pop("caption", None)
    return result


# ── SigLIP2 Per-User Index ──
# Lazily loaded model (shared across users)
_siglip2_model = None
_siglip2_processor = None
_siglip2_device = None


def _build_user_siglip2_index(uid: int, locomo_sample: dict, tmp_dir: str) -> None:
    """Collect all image paths from the converted sample, embed with SigLIP2,
    and save a per-user index to ``{tmp_dir}/u{uid}_siglip2_index.npz``.

    Skips if the target ``.npz`` already exists (idempotent) or
    if the user has no images.
    """
    global _siglip2_model, _siglip2_processor, _siglip2_device

    index_path = os.path.join(tmp_dir, f"u{uid}_siglip2_index.npz")
    if os.path.exists(index_path):
        print(f"  SigLIP2 index already exists: {index_path}")
        return

    # Collect all image paths from conversation turns
    image_paths: list[Path] = []
    for key, value in locomo_sample.get("conversation", {}).items():
        if key.startswith("session_") and isinstance(value, list):
            for turn in value:
                if isinstance(turn, dict):
                    paths = turn.get("image_path")
                    if paths:
                        if isinstance(paths, str):
                            image_paths.append(Path(paths))
                        elif isinstance(paths, list):
                            image_paths.extend(Path(p) for p in paths)

    if not image_paths:
        print(f"  [{uid}] No images found, skipping SigLIP2 index.")
        return

    # Deduplicate and sort
    image_paths = sorted(set(image_paths))
    print(f"  [{uid}] Building SigLIP2 index for {len(image_paths)} images...")

    # Lazy-load the model once
    if _siglip2_model is None:
        import torch
        from transformers import AutoModel, AutoProcessor

        _siglip2_device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  Loading SigLIP2 model on {_siglip2_device}...")
        _siglip2_model = AutoModel.from_pretrained(
            "google/siglip2-base-patch16-224"
        ).to(_siglip2_device)
        _siglip2_processor = AutoProcessor.from_pretrained(
            "google/siglip2-base-patch16-224"
        )
        _siglip2_model.eval()

    # Ensure the project root is on sys.path for membase imports
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.normpath(os.path.join(_script_dir, ".."))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from membase.utils.siglip2_search import embed_images, save_index

    valid_paths, embeddings = embed_images(
        _siglip2_model,
        _siglip2_processor,
        image_paths,
        batch_size=16,
        device=_siglip2_device,
    )
    save_index(Path(index_path), valid_paths, embeddings)
    print(f"  -> {index_path} ({len(valid_paths)} images, dim {embeddings.shape[1]})")


if __name__ == "__main__":
    main()
