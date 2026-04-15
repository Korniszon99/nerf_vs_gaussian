"""Regression tests for the standalone preprocessing script."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from preprocess import (
    BLENDER_SPLIT_FILES,
    _ensure_ffmpeg_available,
    _prepare_windows_input_staging,
    run_ns_process_data,
    split_frames,
    write_blender_split_files,
)


def _fake_tiff_to_png(source_file: Path, destination_file: Path) -> bool:
    """Helper for tests: emulate successful TIFF->PNG conversion."""
    _ = source_file
    destination_file.write_bytes(b"fake png")
    return True


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

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    def test_run_ns_process_data_prefers_images_subdirectory(self, mock_run, _mock_which) -> None:
        """`ns-process-data` should receive `dataset/images` when that folder exists."""
        mock_completed = MagicMock()
        mock_completed.stdout = "ok\n"
        mock_completed.stderr = ""
        mock_completed.returncode = 0
        mock_run.return_value = mock_completed

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "frame_001.jpg").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        command = mock_run.call_args.args[0]
        data_index = command.index("--data") + 1
        self.assertEqual(Path(command[data_index]), images_dir)

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_prefers_dataset_root_when_sparse_layout_exists(self, mock_run, _mock_which) -> None:
        """COLMAP layout should keep the dataset root visible to `ns-process-data`."""
        mock_completed = MagicMock()
        mock_completed.stdout = "ok\n"
        mock_completed.stderr = ""
        mock_completed.returncode = 0
        mock_run.return_value = mock_completed

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            sparse_dir = input_dir / "sparse" / "0"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            sparse_dir.mkdir(parents=True)
            (images_dir / "IMG_2105 .tif").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=True)

        command = mock_run.call_args.args[0]
        data_index = command.index("--data") + 1
        self.assertEqual(Path(command[data_index]), input_dir)
        self.assertIn("--skip-colmap", command)
        self.assertIn("--no-same-dimensions", command)

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_with_windows_staging_after_initial_tiff_failure(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
    ) -> None:
        """On Windows TIFF datasets, a first failure should retry against sanitized staged input."""
        first_run = MagicMock(returncode=1, stdout="", stderr="ffmpeg failed")
        second_run = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mock_run.side_effect = [first_run, second_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG_2105 .tif").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertEqual(mock_run.call_count, 2)
        first_command = mock_run.call_args_list[0].args[0]
        first_data_index = first_command.index("--data") + 1
        self.assertEqual(Path(first_command[first_data_index]), images_dir)

        second_command = mock_run.call_args_list[1].args[0]
        second_data_index = second_command.index("--data") + 1
        staged_images_dir = Path(second_command[second_data_index])
        self.assertEqual(staged_images_dir.name, "images")
        self.assertIn("ns_preprocess_staging_", str(staged_images_dir.parent))
        self.assertTrue((staged_images_dir / "frame_000000.png").is_file())
        self.assertEqual(Path(second_command[second_data_index]), staged_images_dir)

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_with_staging_root_after_staged_images_retry_fails(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
    ) -> None:
        """A failed retry on staged images should do one more retry using the staging root."""
        first_run = MagicMock(returncode=1, stdout="", stderr="initial fail")
        second_run = MagicMock(returncode=1, stdout="", stderr="staged images fail")
        third_run = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mock_run.side_effect = [first_run, second_run, third_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG_2105 .tif").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertEqual(mock_run.call_count, 3)

        second_command = mock_run.call_args_list[1].args[0]
        second_data_index = second_command.index("--data") + 1
        staged_images_dir = Path(second_command[second_data_index])
        self.assertEqual(staged_images_dir.name, "images")

        third_command = mock_run.call_args_list[2].args[0]
        third_data_index = third_command.index("--data") + 1
        self.assertEqual(Path(third_command[third_data_index]), staged_images_dir.parent)
        self.assertIn("--no-same-dimensions", third_command)

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_with_skip_image_processing_after_ffmpeg_failure(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
    ) -> None:
        """A Windows ffmpeg error should trigger one final retry with --skip-image-processing."""
        first_run = MagicMock(returncode=1, stdout="", stderr="initial fail")
        second_run = MagicMock(returncode=1, stdout="", stderr="staged images fail")
        third_run = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error running command: ffmpeg -y -i input.png output.png",
        )
        fourth_run = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mock_run.side_effect = [first_run, second_run, third_run, fourth_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG_2105 .tif").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertEqual(mock_run.call_count, 4)

        third_command = mock_run.call_args_list[2].args[0]
        third_data_index = third_command.index("--data") + 1
        third_data_dir = Path(third_command[third_data_index])

        fourth_command = mock_run.call_args_list[3].args[0]
        fourth_data_index = fourth_command.index("--data") + 1
        self.assertEqual(Path(fourth_command[fourth_data_index]), third_data_dir)
        self.assertIn("--skip-image-processing", fourth_command)

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_reports_last_retry_input_when_all_retries_fail(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
    ) -> None:
        """Failure details should report the final staging-root retry input directory."""
        first_run = MagicMock(returncode=1, stdout="", stderr="initial fail")
        second_run = MagicMock(returncode=1, stdout="", stderr="staged images fail")
        third_run = MagicMock(returncode=1, stdout="", stderr="staging root fail")
        mock_run.side_effect = [first_run, second_run, third_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG_2105 .tif").write_text("fake image")

            with self.assertRaises(RuntimeError) as ctx:
                run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertEqual(mock_run.call_count, 3)
        third_command = mock_run.call_args_list[2].args[0]
        third_data_index = third_command.index("--data") + 1
        staging_root = Path(third_command[third_data_index])

        self.assertIn("staging root fail", str(ctx.exception))
        self.assertIn(f"Retry input directory: {staging_root}", str(ctx.exception))

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retry_preserves_sparse_layout_with_skip_colmap(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
    ) -> None:
        """Retry path should pass staged dataset root and preserve sparse/0 when skip_colmap is enabled."""
        first_run = MagicMock(returncode=1, stdout="", stderr="first attempt failed")
        second_run = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mock_run.side_effect = [first_run, second_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            sparse_zero_dir = input_dir / "sparse" / "0"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            sparse_zero_dir.mkdir(parents=True)
            (images_dir / "frame_0001.tiff").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=True)

        self.assertEqual(mock_run.call_count, 2)
        second_command = mock_run.call_args_list[1].args[0]
        second_data_index = second_command.index("--data") + 1
        staged_root = Path(second_command[second_data_index])
        self.assertIn("ns_preprocess_staging_", str(staged_root))
        self.assertTrue((staged_root / "sparse" / "0").is_dir())
        self.assertTrue((staged_root / "images" / "frame_000000.png").is_file())
        self.assertEqual(Path(second_command[second_data_index]), staged_root)
        self.assertIn("--skip-colmap", second_command)

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_for_unsafe_filenames_with_spaces(self, mock_run, _mock_which) -> None:
        """Unsafe filenames with spaces should trigger staging retry even without TIFF files."""
        first_run = MagicMock(returncode=1, stdout="", stderr="parse error")
        second_run = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mock_run.side_effect = [first_run, second_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG 2105 .jpg").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertEqual(mock_run.call_count, 2)
        second_command = mock_run.call_args_list[1].args[0]
        second_data_index = second_command.index("--data") + 1
        staged_images_dir = Path(second_command[second_data_index])
        self.assertIn("ns_preprocess_staging_", str(staged_images_dir.parent))
        self.assertTrue((staged_images_dir / "frame_000000.jpg").is_file())
        self.assertEqual(Path(second_command[second_data_index]), staged_images_dir)

    @patch("preprocess.sys.platform", "win32")
    def test_prepare_windows_input_staging_falls_back_when_tempfile_creation_fails(self) -> None:
        """When temp staging cannot be created, fallback path should still produce staged images."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG 0001.jpg").write_text("fake image")

            with patch("preprocess.tempfile.mkdtemp", side_effect=OSError("temp unavailable")):
                staged_dir = _prepare_windows_input_staging(
                    input_dir=input_dir,
                    process_input_dir=images_dir,
                    skip_colmap=False,
                )

            self.assertEqual(staged_dir.parent.name, "_preprocess_staging")
            self.assertTrue((staged_dir / "frame_000000.jpg").is_file())

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    def test_run_ns_process_data_uses_stdout_when_stderr_is_empty(self, mock_run, _mock_which) -> None:
        """Regression: stdout-only failures must not collapse to `no stderr captured`."""
        mock_completed = MagicMock()
        mock_completed.stdout = "COLMAP failed: no features found\n"
        mock_completed.stderr = ""
        mock_completed.returncode = 1
        mock_run.return_value = mock_completed

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            output_dir = Path(tmp_dir) / "out"
            input_dir.mkdir(parents=True)

            with self.assertRaises(RuntimeError) as ctx:
                run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertIn("exit code 1", str(ctx.exception))
        self.assertIn("COLMAP failed: no features found", str(ctx.exception))
        self.assertNotIn("no stderr captured", str(ctx.exception))

    @patch("preprocess.which", return_value=None)
    def test_ensure_ffmpeg_available_raises_clear_error_when_missing(self, _mock_which) -> None:
        with self.assertRaises(EnvironmentError) as ctx:
            _ensure_ffmpeg_available()

        self.assertIn("Could not find ffmpeg on PATH", str(ctx.exception))
        self.assertIn("ffmpeg.exe", str(ctx.exception))
