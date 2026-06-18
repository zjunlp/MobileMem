"""Lightweight architecture smoke tests for the pipeline DAG.

These tests intentionally avoid real LLM/image/OCR/face work. They verify the
cheap invariants that keep the refactor usable: graph validity, important
dependency edges, media path routing, and import compatibility.
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipeline import dag  # noqa: E402
from pipeline.spec import RunContext  # noqa: E402


class PipelineDagSmokeTest(unittest.TestCase):
    def test_graph_validates_and_keeps_required_edges(self) -> None:
        dag.validate()

        self.assertIn("sub_events", dag.NODES["conversation"].depends_on)
        self.assertIn("sub_events", dag.NODES["event_photo"].depends_on)
        self.assertIn("event_photo", dag.NODES["document"].depends_on)
        self.assertEqual(dag.topo_order()[0], "profile")
        self.assertEqual(dag.topo_order()[-1], "memory_summary")

    def test_media_adapters_thread_custom_image_dir(self) -> None:
        ctx = RunContext(
            info_dir="C:/tmp/info",
            output_dir="C:/tmp/run/data",
            image_dir="C:/tmp/run/image",
            prompts_dir="C:/tmp/prompts",
            max_workers=2,
            uuid_filter=[7],
            force=True,
        )

        adapters = [
            dag._argv_conversation,
            dag._argv_app_trace,
            dag._argv_event_photo,
            dag._argv_document,
            dag._argv_scenery,
            dag._argv_memory_summary,
        ]
        for adapter in adapters:
            argv = adapter(ctx)
            with self.subTest(adapter=adapter.__name__):
                self.assertIn(ctx.image_dir, argv)
                self.assertTrue(any(str(item).startswith(ctx.output_dir) for item in argv))
                self.assertIn("--force", argv)

    def test_pipeline_import_surface(self) -> None:
        modules = [
            "pipeline.cli",
            "pipeline.dag",
            "generation.profile",
            "generation.life_state",
            "generation.timeline_dates",
            "generation.annual_events",
            "generation.conversation.generator",
            "generation.event_photo.generator",
            "generation.memory_summary",
        ]
        for module in modules:
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_dag_output_verification_rejects_missing_and_empty_required_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext(
                info_dir=str(Path(tmp) / "info"),
                output_dir=str(Path(tmp) / "data"),
                image_dir=str(Path(tmp) / "image"),
                prompts_dir=str(Path(tmp) / "prompts"),
            )
            Path(ctx.output_dir).mkdir(parents=True)

            node = dag.NODES["event_photo"]
            with self.assertRaisesRegex(RuntimeError, "required output"):
                dag.verify_node_outputs(ctx, node)

            Path(ctx.data_path("stage7_1_event_images.jsonl")).write_text("", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "wrote no records"):
                dag.verify_node_outputs(ctx, node)

    def test_dag_output_verification_allows_empty_optional_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext(
                info_dir=str(Path(tmp) / "info"),
                output_dir=str(Path(tmp) / "data"),
                image_dir=str(Path(tmp) / "image"),
                prompts_dir=str(Path(tmp) / "prompts"),
            )
            Path(ctx.output_dir).mkdir(parents=True)
            Path(ctx.data_path("stage7_2_app_screenshots.jsonl")).write_text("", encoding="utf-8")

            dag.verify_node_outputs(ctx, dag.NODES["app_trace"])

    def test_memory_merge_manifest_image_filter(self) -> None:
        memory_summary = importlib.import_module("generation.memory_summary")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "output" / "data"
            image_dir = Path(tmp) / "output" / "image" / "uid0" / "event"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "0_event_0.png"
            image_path.write_bytes(b"not-a-real-png")

            ok = {"image_path": str(image_path), "success": True}
            failed = {"image_path": str(image_path), "success": False}
            missing = {"image_path": str(image_dir / "missing.png"), "success": True}

            self.assertTrue(memory_summary._manifest_image_exists(ok, str(data_dir)))
            self.assertFalse(memory_summary._manifest_image_exists(failed, str(data_dir)))
            self.assertFalse(memory_summary._manifest_image_exists(missing, str(data_dir)))


if __name__ == "__main__":
    unittest.main()
