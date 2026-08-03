#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert Stage5/Stage6 JSONL data into Locomo files.

Supported Stage5 inputs:
- Wrapped JSON: {"summary": ..., "users": [{"user_id": ..., "records": [...]}]}
- JSONL: one top-level Stage5 persona record per line
- JSON list: a list of top-level Stage5 persona records

Supported Stage6 inputs:
- One JSONL file containing one or more records:
  {"uuid": 0, "language": "Chinese", "questions": [...]}
- A directory containing per-user files named stage6_questions_uuid{uid}.jsonl
"""

import argparse
import glob
import json
import os
import sys
from typing import Dict, List, Optional


_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from Raw2Locomo import (  # noqa: E402
    convert_user,
    load_image_summaries,
    remove_visual_fields,
)


def wrap_stage5_record(record: dict) -> dict:
    uid = record.get("uuid")
    if uid is None:
        raise ValueError("Stage5 record missing `uuid`.")
    return {
        "user_id": uid,
        "records": [record],
    }


def build_stage5_wrapper(users: List[dict]) -> dict:
    user_ids = [user["user_id"] for user in users]
    total_sessions = sum(
        len(record.get("sessions", []))
        for user in users
        for record in user.get("records", [])
    )
    return {
        "summary": {
            "user_ids": user_ids,
            "user_count": len(users),
            "total_sessions": total_sessions,
        },
        "users": users,
    }


def load_stage5_any(path: str) -> dict:
    """Load Stage5 from wrapped JSON or top-level-record JSONL."""
    if path.lower().endswith(".jsonl"):
        users = []
        with open(path, encoding="utf-8") as file:
            for line_no, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    users.append(wrap_stage5_record(json.loads(line)))
                except Exception as exc:
                    raise ValueError(f"Failed to parse Stage5 JSONL line {line_no}: {exc}") from exc
        return build_stage5_wrapper(users)

    with open(path, encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict) and isinstance(data.get("users"), list):
        return data
    if isinstance(data, list):
        return build_stage5_wrapper([wrap_stage5_record(record) for record in data])

    raise ValueError(
        "Unsupported Stage5 format. Expected wrapped JSON, JSONL persona records, or JSON list."
    )


def load_stage6_jsonl(path: str) -> Dict[int, dict]:
    """Load one Stage6 JSONL file and wrap records for Raw2Locomo.convert_user()."""
    stage6_by_uid: Dict[int, dict] = {}
    with open(path, encoding="utf-8") as file:
        for line_no, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception as exc:
                raise ValueError(f"Failed to parse Stage6 JSONL line {line_no} in {path}: {exc}") from exc

            uid = record.get("uuid")
            if uid is None:
                continue
            stage6_by_uid[uid] = {
                "user_id": uid,
                "records": [record],
            }
    return stage6_by_uid


def load_stage6_dir(path: str, target_uids: Optional[List[int]]) -> Dict[int, dict]:
    """Load per-user Stage6 files from a directory."""
    if target_uids:
        files = [
            os.path.join(path, f"stage6_questions_uuid{uid}.jsonl")
            for uid in target_uids
        ]
    else:
        files = sorted(glob.glob(os.path.join(path, "stage6_questions_uuid*.jsonl")))

    stage6_by_uid: Dict[int, dict] = {}
    for file_path in files:
        if not os.path.exists(file_path):
            print(f"  WARNING: missing Stage6 file: {file_path}")
            continue
        stage6_by_uid.update(load_stage6_jsonl(file_path))
    return stage6_by_uid


def load_stage6_any(
    stage6_jsonl: Optional[str],
    stage6_dir: Optional[str],
    target_uids: Optional[List[int]],
) -> Dict[int, dict]:
    """Load Stage6 from a JSONL file or a directory of per-user JSONL files."""
    if stage6_dir:
        return load_stage6_dir(stage6_dir, target_uids)
    if stage6_jsonl and os.path.isdir(stage6_jsonl):
        return load_stage6_dir(stage6_jsonl, target_uids)
    if stage6_jsonl:
        return load_stage6_jsonl(stage6_jsonl)
    raise ValueError("Please provide --stage6-jsonl or --stage6-dir.")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Stage5 + Stage6 JSONL data to Locomo format."
    )
    parser.add_argument(
        "--stage5",
        default="data/Raw/stage5.json",
        help="Stage5 data: wrapped JSON or one-persona-per-line JSONL.",
    )
    parser.add_argument(
        "--stage6-jsonl",
        default=None,
        help="Stage6 QA JSONL file. It can contain one user or multiple users.",
    )
    parser.add_argument(
        "--stage6-dir",
        default=None,
        help="Directory containing stage6_questions_uuid{uid}.jsonl files.",
    )
    parser.add_argument(
        "--stage10",
        default="data/Raw/stage10_image_summaries.jsonl",
        help="Optional image caption JSONL. Pass an empty string to disable captions.",
    )
    parser.add_argument("--output-dir", default="data/Locomo", help="Output directory.")
    parser.add_argument("--users", type=int, nargs="+", default=None, help="Target UUIDs. Default: all users.")
    parser.add_argument("--no-image", action="store_true", help="Remove image_path/caption fields from output.")
    parser.add_argument(
        "--no-caption-in-text",
        action="store_true",
        help="Do not append image captions to turn text.",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 60)
    print(f"Loading Stage5: {args.stage5}")
    stage5 = load_stage5_any(args.stage5)
    summary = stage5["summary"]
    print(f"  {summary['user_count']} users, {summary['total_sessions']} sessions")

    target_uids = args.users if args.users is not None else summary["user_ids"]

    stage6_source = args.stage6_dir or args.stage6_jsonl
    print(f"Loading Stage6: {stage6_source}")
    stage6_by_uid = load_stage6_any(args.stage6_jsonl, args.stage6_dir, target_uids)
    print(f"  {len(stage6_by_uid)} users from Stage6")

    if args.stage10:
        print(f"Loading image captions: {args.stage10}")
        image_summary_map = load_image_summaries(args.stage10)
    else:
        print("Image captions disabled.")
        image_summary_map = {}

    print(f"\nProcessing users: {target_uids}")
    converted = 0
    for user_data in stage5["users"]:
        uid = user_data["user_id"]
        if uid not in target_uids:
            continue
        if uid not in stage6_by_uid:
            print(f"  [{uid}] WARNING: no Stage6 data found, skipping")
            continue

        print(f"\n[{uid}] Converting...")
        locomo_sample = convert_user(
            user_data,
            stage6_by_uid[uid],
            image_summary_map,
            args.no_caption_in_text,
        )
        if args.no_image:
            locomo_sample = remove_visual_fields(locomo_sample)

        output_path = os.path.join(args.output_dir, f"locomo_u{uid}.json")
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump([locomo_sample], file, ensure_ascii=False, indent=2)

        actual_sessions = sum(
            1
            for key in locomo_sample["conversation"]
            if key.startswith("session_") and not key.endswith("_date_time")
        )
        print(f"  -> {output_path} ({actual_sessions} sessions, {len(locomo_sample['qa'])} questions)")
        converted += 1

    print(f"\nDone! Converted {converted} users. Output: {args.output_dir}")


if __name__ == "__main__":
    main()
