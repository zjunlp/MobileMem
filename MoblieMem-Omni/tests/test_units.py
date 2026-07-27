"""Pure-function unit tests (no LLM / network / output-dir I/O).

Covers name generation, social-name classification and fixing, tolerant JSON
parsing, truncated-JSON repair, and sub-event expansion for imaging.
"""

from __future__ import annotations

import importlib
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backends.llm.request import _loads_tolerant, _try_fix_truncated_json  # noqa: E402
from generation.annual_events.names import _merge_and_sort_events  # noqa: E402
from generation.event_expansion import expand_events_for_imaging  # noqa: E402
from generation.name_pools import (  # noqa: E402
    EN_FIRST_POOL,
    EN_LAST_POOL,
    GIVEN_POOL,
    SURNAME_POOL,
    make_unique_name,
)
from generation.social_name_fix import apply_fixes, classify_name  # noqa: E402


class MakeUniqueNameTest(unittest.TestCase):
    def test_chinese_first_available_combination(self) -> None:
        self.assertEqual(make_unique_name(set(), is_chinese=True), "宋昊")

    def test_chinese_skips_existing(self) -> None:
        existing = {"宋昊"}
        name = make_unique_name(existing, is_chinese=True)
        self.assertEqual(name, "宋晨")
        self.assertNotIn(name, existing)

    def test_chinese_with_surname(self) -> None:
        self.assertEqual(make_unique_name(set(), surname="张", is_chinese=True), "张昊")

    def test_chinese_surname_taken_falls_back_to_pool(self) -> None:
        existing = {"张昊"}
        self.assertEqual(make_unique_name(existing, surname="张", is_chinese=True), "张晨")

    def test_english_first_available_combination(self) -> None:
        self.assertEqual(make_unique_name(set(), is_chinese=False), "James Smith")

    def test_english_with_surname(self) -> None:
        self.assertEqual(make_unique_name(set(), surname="Lee", is_chinese=False), "James Lee")

    def test_chinese_pool_exhausted_appends_number(self) -> None:
        existing = {s + g for s, g in itertools.product(SURNAME_POOL, GIVEN_POOL)}
        self.assertEqual(make_unique_name(existing, is_chinese=True), "宋昊2")
        existing.add("宋昊2")
        self.assertEqual(make_unique_name(existing, is_chinese=True), "宋昊3")

    def test_english_pool_exhausted_appends_number(self) -> None:
        existing = {f"{f} {last}" for f, last in itertools.product(EN_FIRST_POOL, EN_LAST_POOL)}
        self.assertEqual(make_unique_name(existing, is_chinese=False), "James Smith 2")

    def test_never_returns_existing_name(self) -> None:
        existing = {"宋昊", "宋晨", "宋睿"}
        name = make_unique_name(existing, is_chinese=True)
        self.assertNotIn(name, existing)


class ClassifyNameTest(unittest.TestCase):
    def test_a1_pure_relation_word_chinese(self) -> None:
        self.assertEqual(classify_name("母亲", "母亲"), "A1")

    def test_a1_pure_relation_word_english(self) -> None:
        self.assertEqual(classify_name("Mom", "mother"), "A1")

    def test_a2_surname_plus_relation_abbreviation(self) -> None:
        self.assertEqual(classify_name("张母", "母亲"), "A2")

    def test_a3_key_equals_rel_type(self) -> None:
        self.assertEqual(classify_name("同事", "同事"), "A3")

    def test_b1_surname_plus_title_chinese(self) -> None:
        self.assertEqual(classify_name("李老师", "老师"), "B1")

    def test_b1_title_prefix_english(self) -> None:
        self.assertEqual(classify_name("Coach Smith", "coach"), "B1")

    def test_b3_prefix_plus_real_name(self) -> None:
        self.assertEqual(classify_name("室友李明", "室友"), "B3")

    def test_ok_normal_chinese_name(self) -> None:
        self.assertEqual(classify_name("张明远", "朋友"), "OK")

    def test_ok_normal_english_name(self) -> None:
        self.assertEqual(classify_name("Emily Grace Thompson", "friend"), "OK")

    def test_unknown_long_description(self) -> None:
        self.assertEqual(
            classify_name("那个在图书馆认识的戴眼镜的男生", "认识的人"), "UNKNOWN")


class ApplyFixesTest(unittest.TestCase):
    def test_normal_replacement(self) -> None:
        social_rel = {
            "母亲": {"relationship_type": "母亲"},
            "张明远": {"relationship_type": "朋友"},
        }
        global_names = {"李华"}
        fixed, changes = apply_fixes(social_rel, {"母亲": "王秀兰"}, global_names)

        self.assertEqual(list(fixed.keys()), ["王秀兰", "张明远"])
        self.assertEqual(fixed["王秀兰"], {"relationship_type": "母亲"})
        self.assertEqual(changes, ['"母亲" -> "王秀兰"'])
        self.assertIn("王秀兰", global_names)

    def test_conflicting_new_name_falls_back(self) -> None:
        social_rel = {
            "母亲": {"relationship_type": "母亲"},
            "张明远": {"relationship_type": "朋友"},
        }
        global_names = {"李华"}
        # LLM proposed a name that collides with an existing key.
        fixed, changes = apply_fixes(social_rel, {"母亲": "张明远"}, global_names)

        self.assertEqual(list(fixed.keys()), ["宋昊", "张明远"])
        self.assertEqual(changes, ['"母亲" -> "张明远" (conflict) -> "宋昊"'])
        self.assertIn("宋昊", global_names)

    def test_keys_not_in_fixes_kept_verbatim(self) -> None:
        info = {"relationship_type": "朋友", "description": "高中同学"}
        social_rel = {"张明远": info}
        fixed, changes = apply_fixes(social_rel, {}, set())

        self.assertEqual(fixed, {"张明远": info})
        self.assertEqual(changes, [])


class LoadsTolerantTest(unittest.TestCase):
    def test_strict_json_passes_through(self) -> None:
        self.assertEqual(_loads_tolerant('{"a": 1, "b": [true, null]}'),
                         {"a": 1, "b": [True, None]})

    def test_repairs_comments_and_trailing_commas(self) -> None:
        dialect = (
            '{\n'
            '  // full-line comment\n'
            '  "a": 1, // inline comment\n'
            '  "b": [1, 2,],\n'
            '}'
        )
        self.assertEqual(_loads_tolerant(dialect), {"a": 1, "b": [1, 2]})

    def test_url_in_string_survives_repair(self) -> None:
        # Trailing comma forces the repair path; the // in the URL must survive.
        dialect = '{"url": "http://example.com/page", "a": 1,}'
        self.assertEqual(_loads_tolerant(dialect),
                         {"url": "http://example.com/page", "a": 1})

    def test_garbage_still_raises(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            _loads_tolerant("definitely not json")


class TryFixTruncatedJsonTest(unittest.TestCase):
    def test_truncated_object_gets_closed(self) -> None:
        self.assertEqual(_try_fix_truncated_json('{"a": [1, 2'), '{"a": [1, 2]}')

    def test_truncated_nested_list_gets_closed(self) -> None:
        fixed = _try_fix_truncated_json('[{"a": 1}, {"b": 2')
        self.assertEqual(fixed, '[{"a": 1}, {"b": 2}]')
        self.assertEqual(json.loads(fixed), [{"a": 1}, {"b": 2}])

    def test_balanced_input_returns_none(self) -> None:
        self.assertIsNone(_try_fix_truncated_json('{"a": 1}'))


class MergeAndSortEventsTest(unittest.TestCase):
    """event_id is a downstream foreign key: once assigned it must never change."""

    @staticmethod
    def _evt(event_id, name, start):
        evt = {"event_name": name, "event_start_time": start}
        if event_id is not None:
            evt["event_id"] = event_id
        return evt

    def test_existing_ids_stable_new_ids_appended_list_time_sorted(self) -> None:
        # Existing ids [0, 1, 2] with out-of-order times.
        existing = [
            self._evt(0, "E0", "2025-05-01 10:00:00"),
            self._evt(1, "E1", "2025-02-01 10:00:00"),
            self._evt(2, "E2", "2025-08-01 10:00:00"),
        ]
        new = [
            self._evt(None, "N0", "2025-01-01 10:00:00"),
            self._evt(None, "N1", "2025-06-01 10:00:00"),
        ]
        merged = _merge_and_sort_events(existing, new, total_desired=10)

        # List is time-sorted, old ids untouched, new events got 3 and 4.
        self.assertEqual([e["event_name"] for e in merged],
                         ["N0", "E1", "E0", "N1", "E2"])
        self.assertEqual([e["event_id"] for e in merged], [3, 1, 0, 4, 2])

    def test_truncation_drops_highest_ids_only(self) -> None:
        existing = [
            self._evt(0, "E0", "2025-05-01 10:00:00"),
            self._evt(1, "E1", "2025-02-01 10:00:00"),
            self._evt(2, "E2", "2025-08-01 10:00:00"),
        ]
        new = [
            self._evt(None, "N0", "2025-01-01 10:00:00"),
            self._evt(None, "N1", "2025-06-01 10:00:00"),
        ]
        merged = _merge_and_sort_events(existing, new, total_desired=4)

        # The newest id (4, i.e. N1) is dropped; ids 0-3 all survive unchanged.
        self.assertEqual([e["event_id"] for e in merged], [3, 1, 0, 2])
        self.assertEqual([e["event_name"] for e in merged],
                         ["N0", "E1", "E0", "E2"])

    def test_no_existing_events_numbers_from_zero(self) -> None:
        new = [
            self._evt(None, "N0", "2025-03-01 10:00:00"),
            self._evt(None, "N1", "2025-01-01 10:00:00"),
        ]
        merged = _merge_and_sort_events([], new, total_desired=10)

        # Ids follow input list order (N0 -> 0, N1 -> 1), list is time-sorted.
        self.assertEqual([e["event_name"] for e in merged], ["N1", "N0"])
        self.assertEqual([e["event_id"] for e in merged], [1, 0])

    def test_llm_provided_fake_id_is_reassigned(self) -> None:
        existing = [self._evt(0, "E0", "2025-06-01 10:00:00")]
        # LLM invented event_id=99; it must be discarded and reassigned.
        new = [self._evt(99, "N0", "2025-01-01 10:00:00")]
        merged = _merge_and_sort_events(existing, new, total_desired=10)

        self.assertEqual([(e["event_id"], e["event_name"]) for e in merged],
                         [(1, "N0"), (0, "E0")])


class ExpandEventsForImagingTest(unittest.TestCase):
    def test_expansion_rules(self) -> None:
        short_event = {"event_id": 0, "duration_type": "short-term"}
        mid_event = {"event_id": 1, "duration_type": "mid-term"}
        long_event = {"event_id": 2, "duration_type": "long-term"}
        intro_child = {"sub_event_id": "1_1", "is_intro": True}
        real_child = {"sub_event_id": "1_2"}
        index = {(7, 1): [intro_child, real_child]}

        result = expand_events_for_imaging(
            7, [short_event, mid_event, long_event], index)

        self.assertEqual(result, [
            (0, short_event),      # short-term kept as-is
            ("1_2", real_child),   # mid-term replaced by children, intro skipped
            (2, long_event),       # no children in index -> original kept
        ])


class MergeAllImagesCaptionJoinTest(unittest.TestCase):
    """Phase 2 joins captions while keeping scenery out of event memories."""

    def test_scenery_lands_only_in_total_images(self) -> None:
        memory_summary = importlib.import_module("generation.memory_summary")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "output" / "data"
            image_dir = root / "output" / "image"
            data_dir.mkdir(parents=True)
            scenery_dir = image_dir / "uid1" / "others"
            scenery_dir.mkdir(parents=True)
            event_dir = image_dir / "uid1" / "camera_photos"
            event_dir.mkdir(parents=True)

            event_png = event_dir / "1_event_0.png"
            scenery_png = scenery_dir / "food_0.png"
            event_png.write_bytes(b"png")
            scenery_png.write_bytes(b"png")

            (image_dir / "manifest.json").write_text(
                json.dumps({"1": {"food": ["food_0.png"]}}), encoding="utf-8")

            # Minimal upstream manifests (paths absolute so _manifest_image_exists works).
            (data_dir / "sub_events.jsonl").write_text(
                json.dumps({
                    "uuid": 1,
                    "sub_events": [{
                        "parent_event_id": 0,
                        "children": [{
                            "sub_event_id": "0_1",
                            "event_name": "demo",
                            "event_start_time": "2025-01-01 10:00:00",
                            "participants": [],
                            "importance": "low",
                        }],
                    }],
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (data_dir / "annual_events.jsonl").write_text(
                json.dumps({"uuid": 1, "Events": []}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (data_dir / "event_images.jsonl").write_text(
                json.dumps({
                    "uuid": 1,
                    "sub_event_id": "0_1",
                    "image_path": str(event_png),
                    "success": True,
                    "participants": [],
                    "scene_prompt": "",
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            for name in ("app_screenshots.jsonl", "document_records.jsonl", "group_chats.jsonl"):
                (data_dir / name).write_text("", encoding="utf-8")

            (data_dir / "image_summaries.jsonl").write_text(
                json.dumps({
                    "image_path": str(event_png),
                    "uuid": 1,
                    "success": True,
                    "summary_zh": "事件图摘要",
                    "summary_en": "",
                }, ensure_ascii=False) + "\n"
                + json.dumps({
                    "image_path": str(scenery_png),
                    "uuid": 1,
                    "success": True,
                    "summary_zh": "风景图摘要",
                    "summary_en": "",
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            merged_out = data_dir / "merged_memories.jsonl"
            memory_summary.merge_all_images(
                data_dir=str(data_dir),
                summaries_file=str(data_dir / "image_summaries.jsonl"),
                merged_output=str(merged_out),
                sub_events_file=str(data_dir / "sub_events.jsonl"),
                events_file=str(data_dir / "annual_events.jsonl"),
                image_dir=str(image_dir),
            )

            rows = [
                json.loads(line)
                for line in merged_out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            by_seid = {r["sub_event_id"]: r for r in rows}
            self.assertIn("0_1", by_seid)
            self.assertNotIn("scenery", by_seid)

            event_imgs = by_seid["0_1"]["images"]
            self.assertEqual(len(event_imgs), 1)
            self.assertIsInstance(event_imgs[0], dict)
            self.assertEqual(event_imgs[0]["summary_zh"], "事件图摘要")
            self.assertTrue(event_imgs[0]["image_path"].endswith("1_event_0.png"))

            total = [
                json.loads(line)
                for line in (data_dir / "total_images.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(total), 2)
            self.assertTrue(any(t.get("summary_zh") == "事件图摘要" for t in total))
            self.assertTrue(any(t.get("summary_zh") == "风景图摘要" for t in total))
            scenery = next(t for t in total if t.get("type") == "scenery")
            self.assertIsNone(scenery["sub_event_id"])


if __name__ == "__main__":
    unittest.main()
