"""Regression tests for single-writer outputs and manifest-based resume."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from infra.store import (  # noqa: E402
    load_manifest_index,
    write_jsonl,
    write_manifest_index_atomic,
)
from pipeline import dag  # noqa: E402
from pipeline.spec import RunContext  # noqa: E402


class _FakePlaywright:
    chromium = None

    def __init__(self):
        self.chromium = self

    def start(self):
        return self

    def launch(self):
        return self

    def new_page(self, **_kwargs):
        return object()

    def close(self):
        return None

    def stop(self):
        return None


def _fake_playwright_modules():
    package = types.ModuleType("playwright")
    package.__path__ = []
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = _FakePlaywright
    return {"playwright": package, "playwright.sync_api": sync_api}


class ManifestStoreTest(unittest.TestCase):
    def test_composite_manifest_upsert_preserves_other_uuids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "app_screenshots.jsonl")
            write_jsonl([
                {"uuid": 1, "sub_event_id": "0_3", "app_type": "book", "info": {"v": 1}},
                {"uuid": 2, "sub_event_id": "0_4", "app_type": "music", "info": {"v": 2}},
            ], path)

            manifest = load_manifest_index(path, "app_type")
            manifest[(1, "0_3", "book")] = {
                "uuid": 1,
                "sub_event_id": "0_3",
                "app_type": "book",
                "info": {"v": 3},
            }
            write_manifest_index_atomic(manifest, path)
            reloaded = load_manifest_index(path, "app_type")

            self.assertEqual(reloaded[(1, "0_3", "book")]["info"], {"v": 3})
            self.assertEqual(reloaded[(2, "0_4", "music")]["info"], {"v": 2})

    def test_generators_hydrate_info_from_their_own_manifests(self) -> None:
        from generation.app_trace import generator as app_trace
        from generation.document import generator as document

        source = [{"uuid": 7, "Events": [{"event_id": "0_3"}]}]
        app_personas = copy.deepcopy(source)
        document_personas = copy.deepcopy(source)

        app_trace._hydrate_info_from_manifest(
            app_personas,
            {(7, "0_3", "book"): {"info": {"title": "cached"}}},
            ["book"],
        )
        document._hydrate_info_from_manifest(
            document_personas,
            {(7, "0_3", "money"): {"money_info": {"amount": 20}}},
            ["money"],
        )

        self.assertEqual(app_personas[0]["Events"][0]["book_info"]["title"], "cached")
        self.assertEqual(document_personas[0]["Events"][0]["money_info"]["amount"], 20)


class OutputOwnershipTest(unittest.TestCase):
    def _context(self, tmp: str) -> RunContext:
        return RunContext(
            info_dir=str(Path(tmp) / "info"),
            output_dir=str(Path(tmp) / "data"),
            image_dir=str(Path(tmp) / "image"),
            prompts_dir=str(Path(tmp) / "prompts"),
        )

    def test_declared_output_owners(self) -> None:
        self.assertEqual(dag.OUTPUT_OWNERS, {
            "annual_events.jsonl": "annual_events",
            "sub_events.jsonl": "sub_events",
            "group_chats.jsonl": "conversation",
            "app_screenshots.jsonl": "app_trace",
            "document_records.jsonl": "document",
            "event_images.jsonl": "event_photo",
        })
        self.assertEqual(dag.NODES["document"].outputs, ("document_records.jsonl",))

    def test_non_owner_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._context(tmp)
            Path(ctx.output_dir).mkdir(parents=True)
            annual_path = Path(ctx.data_path("annual_events.jsonl"))
            annual_path.write_text("before\n", encoding="utf-8")
            snapshot = dag.snapshot_non_owned_outputs(ctx, "app_trace")
            annual_path.write_text("after\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "annual_events.jsonl"):
                dag.assert_non_owned_outputs_unchanged(ctx, "app_trace", snapshot)

    def test_media_adapters_pass_owned_manifest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._context(tmp)
            app_args = dag._argv_app_trace(ctx)
            document_args = dag._argv_document(ctx)
            merge_args = dag._argv_memory_summary(ctx)

            self.assertEqual(
                app_args[app_args.index("--manifest-file") + 1],
                ctx.data_path("app_screenshots.jsonl"),
            )
            self.assertEqual(
                document_args[document_args.index("--manifest-file") + 1],
                ctx.data_path("document_records.jsonl"),
            )
            self.assertEqual(
                merge_args[merge_args.index("--document-file") + 1],
                ctx.data_path("document_records.jsonl"),
            )

    def test_app_trace_dry_run_does_not_rewrite_annual_events(self) -> None:
        from generation.app_trace import generator as app_trace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            annual_path = root / "annual_events.jsonl"
            sub_events_path = root / "sub_events.jsonl"
            image_dir = root / "image"
            app_manifest = root / "app_screenshots.jsonl"
            record = {
                "uuid": 9,
                "Events": [{
                    "event_id": 0,
                    "duration_type": "short-term",
                    "event_name": "test event",
                }],
            }
            annual_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            sub_events_path.write_text("", encoding="utf-8")
            original = annual_path.read_bytes()

            argv = [
                "app_trace",
                "--events-file", str(annual_path),
                "--sub-events-file", str(sub_events_path),
                "--output-dir", str(image_dir),
                "--manifest-file", str(app_manifest),
                "--dry-run",
            ]
            with mock.patch.object(sys, "argv", argv):
                app_trace.main()
            self.assertEqual(annual_path.read_bytes(), original)

    def test_app_trace_second_run_reuses_manifest_info(self) -> None:
        from core import DIR_NAME
        from generation.app_trace import generator as app_trace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            annual_path = root / "annual_events.jsonl"
            sub_events_path = root / "sub_events.jsonl"
            image_dir = root / "image"
            manifest_path = root / "app_screenshots.jsonl"
            annual_path.write_text(json.dumps({
                "uuid": 5,
                "Basic_Profile": {"nationality": "Chinese", "name": "Test"},
                "Events": [{
                    "event_id": 0,
                    "duration_type": "long-term",
                    "event_name": "parent event",
                }],
            }) + "\n", encoding="utf-8")
            sub_events_path.write_text(json.dumps({
                "uuid": 5,
                "sub_events": [{
                    "parent_event_id": 0,
                    "children": [{
                        "sub_event_id": "0_3",
                        "event_name": "read a book",
                        "participants": [],
                    }],
                }],
            }) + "\n", encoding="utf-8")
            original = annual_path.read_bytes()

            argv = [
                "app_trace",
                "--events-file", str(annual_path),
                "--sub-events-file", str(sub_events_path),
                "--output-dir", str(image_dir),
                "--manifest-file", str(manifest_path),
                "--types", "book",
                "--events-per-type", "1",
            ]

            def generate_info(_persona, events, app_type, _nationality):
                return [{"event_id": events[0]["event_id"],
                         f"{app_type}_info": {"title": "cached"}}]

            def render(_page, task, output_dir, _templates, resume=True, **_kwargs):
                path = (Path(output_dir) / f"uid{task['uuid']}" / DIR_NAME[task['app_type']]
                        / f"{task['uuid']}_{task['app_type']}_{task['event_id']}.png")
                if resume and path.exists():
                    return "skipped"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"png")
                return "done"

            original_types = list(app_trace.APP_TYPES)
            generate_mock = mock.Mock(side_effect=generate_info)
            try:
                with mock.patch.dict(sys.modules, _fake_playwright_modules()), \
                        mock.patch.object(app_trace, "_load_template", return_value="<html></html>"), \
                        mock.patch.object(app_trace, "render_single_sync", side_effect=render), \
                        mock.patch.object(app_trace, "_call_llm_generate_info_single", generate_mock):
                    with mock.patch.object(sys, "argv", argv):
                        app_trace.main()
                    with mock.patch.object(sys, "argv", argv):
                        app_trace.main()
            finally:
                app_trace.APP_TYPES[:] = original_types

            self.assertEqual(generate_mock.call_count, 1)
            self.assertEqual(annual_path.read_bytes(), original)
            manifest = load_manifest_index(str(manifest_path), "app_type")
            self.assertEqual(manifest[(5, "0_3", "book")]["info"]["title"], "cached")
            self.assertTrue(manifest[(5, "0_3", "book")]["success"])

    def test_document_second_run_reuses_manifest_info(self) -> None:
        from generation.document import generator as document

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            annual_path = root / "annual_events.jsonl"
            sub_events_path = root / "sub_events.jsonl"
            template_path = root / "money.html"
            image_dir = root / "image"
            manifest_path = root / "document_records.jsonl"
            annual_path.write_text(json.dumps({
                "uuid": 6,
                "Events": [{
                    "event_id": 0,
                    "duration_type": "long-term",
                    "event_name": "parent event",
                }],
            }) + "\n", encoding="utf-8")
            sub_events_path.write_text(json.dumps({
                "uuid": 6,
                "sub_events": [{
                    "parent_event_id": 0,
                    "children": [{
                        "sub_event_id": "0_4",
                        "event_name": "split dinner bill",
                        "participants": [],
                    }],
                }],
            }) + "\n", encoding="utf-8")
            template_path.write_text("<html></html>", encoding="utf-8")
            original = annual_path.read_bytes()

            argv = [
                "document",
                "--types", "money",
                "--events-file", str(annual_path),
                "--sub-events-file", str(sub_events_path),
                "--output-dir", str(image_dir),
                "--image-dir", str(image_dir),
                "--manifest-file", str(manifest_path),
                "--events-per-type", "1",
            ]

            def generate_info(_name, _career, _location, _personality,
                              events, app_type, _nationality):
                return [{"event_id": events[0]["event_id"],
                         f"{app_type}_info": {"amount": 20}}]

            def render(_page, _html, png_path, **_kwargs):
                path = Path(png_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"png")
                return True

            generate_mock = mock.Mock(side_effect=generate_info)
            with mock.patch.dict(sys.modules, _fake_playwright_modules()), \
                    mock.patch.object(document, "TEMPLATES_CN", {"money": str(template_path)}), \
                    mock.patch.object(document, "TEMPLATES_EN", {"money": str(template_path)}), \
                    mock.patch.object(document, "llm_select_events",
                                      side_effect=lambda events, *_args, **_kwargs: events[:1]), \
                    mock.patch.object(document, "call_llm_generate_info", generate_mock), \
                    mock.patch.object(document, "fill_money_template", return_value="<html></html>"), \
                    mock.patch.object(document, "render_screenshot", side_effect=render):
                with mock.patch.object(sys, "argv", argv):
                    document.main()
                with mock.patch.object(sys, "argv", argv):
                    document.main()

            self.assertEqual(generate_mock.call_count, 1)
            self.assertEqual(annual_path.read_bytes(), original)
            manifest = load_manifest_index(str(manifest_path), "type")
            self.assertEqual(manifest[(6, "0_4", "money")]["money_info"]["amount"], 20)
            self.assertTrue(manifest[(6, "0_4", "money")]["success"])

    def test_memory_merge_prefers_new_document_name_with_legacy_fallback(self) -> None:
        from generation import memory_summary

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            preferred = data_dir / "document_records.jsonl"
            legacy = data_dir / "tickets.jsonl"

            self.assertEqual(
                memory_summary._resolve_document_manifest(str(data_dir)),
                str(preferred),
            )
            legacy.write_text("", encoding="utf-8")
            self.assertEqual(
                memory_summary._resolve_document_manifest(str(data_dir)),
                str(legacy),
            )
            preferred.write_text("", encoding="utf-8")
            self.assertEqual(
                memory_summary._resolve_document_manifest(str(data_dir)),
                str(preferred),
            )


if __name__ == "__main__":
    unittest.main()
