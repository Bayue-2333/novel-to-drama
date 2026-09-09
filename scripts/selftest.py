"""Offline regression tests; optional FFmpeg synthetic-media integration test."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bind_workflow as workflow
import preflight
import verify_delivery as delivery


def fixture():
    info = {
        "MiniMaxH3Example": {"python_module": "comfy_extras.nodes_minimax_h3", "output": ["VIDEO"],
                             "input": {"required": {"prompt": ["STRING", {}], "length": ["INT", {"min": 5, "max": 362}]}}},
        "SaveExample": {"output": [], "output_node": True, "input": {"required": {"video": ["VIDEO", {}]}}},
    }
    graph = {"1": {"class_type": "MiniMaxH3Example", "inputs": {"prompt": "old", "length": 124}},
             "2": {"class_type": "SaveExample", "inputs": {"video": ["1", 0]}}}
    plan = {"output_node": "2", "bindings": [{"node": "1", "input": "prompt", "expected": "old", "value": "新提示词"}]}
    return graph, plan, info


class WorkflowTests(unittest.TestCase):
    def test_bind_preserves_source_and_wiring(self):
        graph, plan, info = fixture()
        result = workflow.bind(graph, plan, info)
        self.assertEqual(result["1"]["inputs"]["prompt"], "新提示词")
        self.assertEqual(graph["1"]["inputs"]["prompt"], "old")
        self.assertEqual(result["2"], graph["2"])

    def test_stale_binding(self):
        graph, plan, info = fixture()
        plan["bindings"][0]["expected"] = "wrong"
        with self.assertRaises(ValueError):
            workflow.bind(graph, plan, info)

    def test_ui_export_rejected(self):
        _, plan, info = fixture()
        with self.assertRaises(ValueError):
            workflow.bind({"nodes": []}, plan, info)

    def test_hosted_node_rejected(self):
        graph, plan, info = fixture()
        info["MiniMaxH3Example"]["api_node"] = True
        with self.assertRaises(ValueError):
            workflow.bind(graph, plan, info)

    def test_bad_slot_and_cycle(self):
        graph, _, info = fixture()
        graph["2"]["inputs"]["video"] = ["1", 8]
        with self.assertRaises(ValueError):
            workflow.validate_graph(graph, info, "2")
        graph["2"]["inputs"]["video"] = ["1", 0]
        graph["1"]["inputs"]["cycle"] = ["1", 0]
        with self.assertRaises(ValueError):
            workflow.validate_graph(graph, info, "2")

    def test_link_cannot_be_replaced(self):
        graph, plan, info = fixture()
        plan["bindings"] = [{"node": "2", "input": "video", "expected": ["1", 0], "value": "bad"}]
        with self.assertRaises(ValueError):
            workflow.bind(graph, plan, info)

    def test_range_and_type(self):
        graph, plan, info = fixture()
        for value in (99999, True, 12.5):
            plan["bindings"] = [{"node": "1", "input": "length", "expected": 124, "value": value}]
            with self.assertRaises(ValueError):
                workflow.bind(graph, plan, info)

    def test_model_options(self):
        graph, plan, info = fixture()
        graph["1"]["inputs"]["model"] = "exists.safetensors"
        info["MiniMaxH3Example"]["input"]["required"]["model"] = [["exists.safetensors"]]
        plan["bindings"] = [{"node": "1", "input": "model", "expected": "exists.safetensors", "value": "missing.safetensors"}]
        with self.assertRaises(ValueError):
            workflow.bind(graph, plan, info)

    def test_unused_binding_rejected(self):
        graph, plan, info = fixture()
        graph["3"] = deepcopy(graph["1"])
        plan["bindings"][0]["node"] = "3"
        with self.assertRaises(ValueError):
            workflow.bind(graph, plan, info)


class ReviewTests(unittest.TestCase):
    def test_coverage(self):
        self.assertTrue(delivery.covers([[5, 10], [0, 5]], 10))
        for ranges in ([], [[0, 2], [4, 10]], [[0, 99]], [[0, float("nan")]], [[-1, 10]]):
            self.assertFalse(delivery.covers(ranges, 10))

    def test_missing_review_never_passes(self):
        self.assertTrue(delivery.check_reviews({}, "hash", 10, Path.cwd()))

    def test_hash_changes_with_any_asset(self):
        hashes = {"video": "a", "master": "b", "srt": "c", "ass": "d"}
        initial = delivery.bundle_digest(hashes)
        for key in hashes:
            changed = dict(hashes, **{key: "new"})
            self.assertNotEqual(initial, delivery.bundle_digest(changed))

    def test_subtitle_overrun_and_overlap(self):
        delivery.validate_cues([(0, 1, "你好"), (1, 2, "再见")], 2)
        for cues in ([], [(0, 3, "你好")], [(0, 1.5, "甲"), (1, 2, "乙")], [(0, 1, "")]):
            with self.assertRaises(ValueError):
                delivery.validate_cues(cues, 2)

    def test_invalid_timestamp(self):
        self.assertEqual(delivery.seconds("01:00:01.50"), 3601.5)
        with self.assertRaises(ValueError):
            delivery.seconds("00:60:00,000")

    def test_empty_manifest(self):
        self.assertEqual(delivery.verify({}, Path.cwd(), "absent", "absent")["status"], "needs_review")

    def test_offline_preflight_is_not_ready(self):
        with patch("preflight.urlopen", side_effect=OSError("offline")):
            result, info = preflight.snapshot("http://127.0.0.1:8188", Path.cwd())
        self.assertEqual(result["status"], "needs_setup")
        self.assertFalse(result["generation_verified"])
        self.assertIsNone(info)


def integration(ffmpeg, ffprobe, parent):
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="media-test-", dir=parent) as tmp:
        root = Path(tmp)
        common = [ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=128x224:rate=24",
                  "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]
        delivery.run_command(common + [root / "master.mp4"], 60)
        srt = "1\n00:00:00,200 --> 00:00:01,500\n测试字幕\n"
        ass = """[Script Info]
ScriptType: v4.00+
PlayResX: 128
PlayResY: 224
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,12,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,4,4,12,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.50,Default,,0,0,0,,测试字幕
"""
        (root / "captions.srt").write_text(srt, encoding="utf-8")
        (root / "captions.ass").write_text(ass, encoding="utf-8")
        delivery.run_command([ffmpeg, "-y", "-v", "error", "-i", "master.mp4", "-vf", "ass=captions.ass",
                              "-c:v", "libx264", "-c:a", "copy", "subtitled.mp4"], 60, cwd=root)
        assert delivery.sha256(root / "master.mp4") != delivery.sha256(root / "subtitled.mp4")
        (root / "test-evidence.md").write_text("Synthetic fixture only. Not a real production review.", encoding="utf-8")
        manifest = {"required_episode_ids": ["E01"], "episodes": [{"id": "E01", "video": "subtitled.mp4", "master": "master.mp4",
                    "srt": "captions.srt", "ass": "captions.ass", "expected": {"width": 128, "height": 224, "fps": 24}}]}
        first = delivery.verify(manifest, root, ffprobe, ffmpeg)
        assert first["status"] == "needs_review", first
        row = first["episodes"][0]
        bundle, duration = row["bundle_sha256"], row["video"]["duration"]
        manifest["episodes"][0]["reviews"] = {kind: {"status": "pass", "bundle_sha256": bundle, "ranges": [[0, duration]],
             "evidence": ["test-evidence.md"], "method": "test fixture", "reviewer": "test", "reviewed_at": "test"} for kind in delivery.REVIEW_KINDS}
        result = delivery.verify(manifest, root, ffprobe, ffmpeg)
        assert result["status"] == "pass", result
        (root / "captions.srt").write_text(srt.replace("测试字幕", "字幕变更"), encoding="utf-8")
        assert delivery.verify(manifest, root, ffprobe, ffmpeg)["status"] == "needs_review"
        (root / "captions.ass").write_text(ass.replace("测试字幕", "字幕变更"), encoding="utf-8")
        assert any("stale" in e for e in delivery.verify(manifest, root, ffprobe, ffmpeg)["errors"])
        (root / "master.mp4").write_bytes(b"broken")
        assert delivery.verify(manifest, root, ffprobe, ffmpeg)["status"] == "needs_review"
        print("Synthetic media integration: ASS burn-in/decode, integrity, missing/stale evidence, subtitle drift and damaged media checks passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--work-dir", type=Path, default=Path.cwd() / "work" / "drama-selftest")
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
    if not result.wasSuccessful():
        return 1
    if bool(args.ffmpeg) != bool(args.ffprobe):
        parser.error("Provide both --ffmpeg and --ffprobe")
    if args.ffmpeg:
        integration(args.ffmpeg, args.ffprobe, args.work_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
