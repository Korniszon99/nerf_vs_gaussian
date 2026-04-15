"""Regression tests for the standalone preprocessing script."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from preprocess import BLENDER_SPLIT_FILES, split_frames, write_blender_split_files


class PreprocessSplitTests(SimpleTestCase):
    """Tests for `gs_vs_nerf/preprocess.py` split behavior."""

    def test_split_frames_uses_80_10_10_order(self) -> None:
        """A 10-frame input should split into 8/1/1 frames in original order."""
        frames = [{"frame_id": index} for index in range(10)]

        train_frames, test_frames, val_frames = split_frames(frames)

        self.assertEqual([frame["frame_id"] for frame in train_frames], list(range(8)))
        self.assertEqual([frame["frame_id"] for frame in test_frames], [8])
        self.assertEqual([frame["frame_id"] for frame in val_frames], [9])

    def test_write_blender_split_files_preserves_top_level_metadata(self) -> None:
        """Split JSON files must keep non-frame metadata untouched."""
        transforms_data = {
            "camera_angle_x": 0.691111207,
            "fl_x": 1111.0,
            "fl_y": 1111.0,
            "cx": 512.0,
            "cy": 384.0,
            "meta": {"source": "colmap", "version": 1},
            "frames": [{"file_path": f"frame_{index:03d}.png"} for index in range(10)],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_blender_split_files(transforms_data=transforms_data, output_dir=output_dir)

            expected_frame_slices = {
                BLENDER_SPLIT_FILES[0]: transforms_data["frames"][:8],
                BLENDER_SPLIT_FILES[1]: transforms_data["frames"][8:9],
                BLENDER_SPLIT_FILES[2]: transforms_data["frames"][9:],
            }

            for file_name in BLENDER_SPLIT_FILES:
                payload = json.loads((output_dir / file_name).read_text(encoding="utf-8"))

                self.assertEqual(payload["frames"], expected_frame_slices[file_name])
                self.assertEqual(payload["camera_angle_x"], transforms_data["camera_angle_x"])
                self.assertEqual(payload["fl_x"], transforms_data["fl_x"])
                self.assertEqual(payload["fl_y"], transforms_data["fl_y"])
                self.assertEqual(payload["cx"], transforms_data["cx"])
                self.assertEqual(payload["cy"], transforms_data["cy"])
                self.assertEqual(payload["meta"], transforms_data["meta"])

