"""Regression tests for the standalone preprocessing script."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from preprocess import (
    BLENDER_SPLIT_FILES,
    _create_png_companion_files,
    _ensure_ffmpeg_available,
    _ensure_metadata_in_output_dir,
    _prepare_windows_input_staging,
    _rewrite_frame_file_paths_to_source_images,
    _resolve_ns_process_data_input_dir,
    preprocess_dataset,
    run_ns_process_data,
    save_transforms_json,
    should_skip_colmap,
    split_frames,
    write_blender_split_files,
)


def _fake_tiff_to_png(source_file: Path, destination_file: Path) -> bool:
    """Helper for tests: emulate successful TIFF->PNG conversion."""
    _ = source_file
    destination_file.write_bytes(b"fake png")
    return True


def _fake_image_to_png(source_file: Path, destination_file: Path) -> bool:
    """Helper for tests: emulate generic image->PNG conversion."""
    _ = source_file
    destination_file.write_bytes(b"fake png companion")
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

    def test_write_blender_split_files_derives_camera_angle_x_from_fl_x_and_w(self) -> None:
        """When camera_angle_x is missing, split payload should derive it from fl_x and w."""
        transforms_data = {
            "fl_x": 1000.0,
            "w": 2000,
            "frames": [{"file_path": f"frame_{index:03d}.png"} for index in range(10)],
        }
        expected_camera_angle_x = 2.0 * math.atan(transforms_data["w"] / (2.0 * transforms_data["fl_x"]))

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_blender_split_files(transforms_data=transforms_data, output_dir=output_dir)

            for file_name in BLENDER_SPLIT_FILES:
                payload = json.loads((output_dir / file_name).read_text(encoding="utf-8"))
                self.assertIn("camera_angle_x", payload)
                self.assertAlmostEqual(payload["camera_angle_x"], expected_camera_angle_x)

    def test_should_skip_colmap_requires_complete_colmap_files_not_only_sparse_directory(self) -> None:
        """sparse/0 directory alone must not imply COLMAP can be skipped."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            sparse_zero = input_dir / "sparse" / "0"
            sparse_zero.mkdir(parents=True)
            (sparse_zero / "cameras.bin").write_bytes(b"partial")

            with self.assertLogs("preprocess", level="WARNING") as captured_logs:
                self.assertFalse(should_skip_colmap(input_dir=input_dir, skip_colmap_flag=True))

            self.assertFalse(should_skip_colmap(input_dir=input_dir, skip_colmap_flag=False))
            self.assertIn("COLMAP results are incomplete", "\n".join(captured_logs.output))

    def test_resolve_ns_process_data_input_dir_autocorrects_images_path_when_parent_has_sparse(self) -> None:
        """If caller passes dataset/images and parent has sparse/0, resolver must return dataset root and warn."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_dir = Path(tmp_dir) / "dataset"
            images_dir = dataset_dir / "images"
            images_dir.mkdir(parents=True)
            (dataset_dir / "sparse" / "0").mkdir(parents=True)
            (images_dir / "frame_001.jpg").write_text("fake image")

            with self.assertLogs("preprocess", level="WARNING") as captured_logs:
                resolved_dir = _resolve_ns_process_data_input_dir(images_dir)

            self.assertEqual(resolved_dir, dataset_dir)
            self.assertIn("Input directory points to images/", "\n".join(captured_logs.output))

    def test_ensure_metadata_in_output_dir_copies_transforms_from_nested_output_location(self) -> None:
        """If transforms.json is nested under output_dir, it should be copied to output root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "out"
            nested_output = output_dir / "nested" / "ns"
            output_dir.mkdir(parents=True)
            nested_output.mkdir(parents=True)

            nested_transforms = nested_output / "transforms.json"
            nested_payload = "{\"frames\": []}"
            nested_transforms.write_text(nested_payload, encoding="utf-8")

            completed = MagicMock(stdout="ok", stderr="", returncode=0)
            copied_path = _ensure_metadata_in_output_dir(
                output_dir=output_dir,
                source_dir=output_dir,
                process_output=completed,
                skip_colmap=False,
                input_dir=output_dir,
            )

            self.assertEqual(copied_path, output_dir / "transforms.json")
            self.assertEqual((output_dir / "transforms.json").read_text(encoding="utf-8"), nested_payload)

    def test_ensure_metadata_in_output_dir_copies_transforms_from_nested_source_location(self) -> None:
        """If transforms.json is written under staged source subdirectories, it should be copied to output root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "out"
            source_dir = Path(tmp_dir) / "stage"
            nested_source = source_dir / "images"
            output_dir.mkdir(parents=True)
            nested_source.mkdir(parents=True)

            nested_transforms = nested_source / "transforms.json"
            nested_payload = "{\"frames\": [{\"file_path\": \"frame_000.png\"}]}"
            nested_transforms.write_text(nested_payload, encoding="utf-8")

            completed = MagicMock(stdout="ok", stderr="", returncode=0)
            copied_path = _ensure_metadata_in_output_dir(
                output_dir=output_dir,
                source_dir=source_dir,
                process_output=completed,
                skip_colmap=False,
                input_dir=source_dir,
            )

            self.assertEqual(copied_path, output_dir / "transforms.json")
            self.assertEqual((output_dir / "transforms.json").read_text(encoding="utf-8"), nested_payload)

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    def test_run_ns_process_data_prefers_images_subdirectory(self, mock_run, _mock_which, _mock_ensure_metadata) -> None:
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

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_prefers_dataset_root_when_sparse_layout_exists(self, mock_run, _mock_which, _mock_ensure_metadata) -> None:
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
        colmap_index = command.index("--colmap-model-path") + 1
        self.assertEqual(Path(command[colmap_index]), sparse_dir)
        self.assertIn("--no-same-dimensions", command)

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    def test_run_ns_process_data_skip_colmap_omits_colmap_model_path_when_sparse_is_missing(
        self,
        mock_run,
        _mock_which,
        _mock_ensure_metadata,
    ) -> None:
        """skip_colmap without any sparse/0 should not add --colmap-model-path."""
        mock_completed = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mock_run.return_value = mock_completed

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "frame_001.jpg").write_text("fake image")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=True)

        command = mock_run.call_args.args[0]
        self.assertIn("--skip-colmap", command)
        self.assertNotIn("--colmap-model-path", command)

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_with_windows_staging_after_initial_tiff_failure(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
        _mock_ensure_metadata,
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

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_with_staging_root_after_staged_images_retry_fails(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
        _mock_ensure_metadata,
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

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retries_with_skip_image_processing_after_ffmpeg_failure(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
        _mock_ensure_metadata,
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
    def test_run_ns_process_data_reports_error_when_skip_image_processing_retry_also_fails(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
    ) -> None:
        """When the final --skip-image-processing retry fails, surfaced error should include that failure."""
        first_run = MagicMock(returncode=1, stdout="", stderr="initial fail")
        second_run = MagicMock(returncode=1, stdout="", stderr="staged images fail")
        third_run = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error running command: ffmpeg -y -i input.png output.png",
        )
        fourth_run = MagicMock(returncode=1, stdout="", stderr="skip-image-processing retry failed")
        mock_run.side_effect = [first_run, second_run, third_run, fourth_run]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            output_dir = Path(tmp_dir) / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "IMG_2105 .tif").write_text("fake image")

            with self.assertRaises(RuntimeError) as ctx:
                run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        self.assertEqual(mock_run.call_count, 4)
        self.assertIn("skip-image-processing retry failed", str(ctx.exception))
        self.assertIn("Retry input directory:", str(ctx.exception))

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

    @patch("preprocess._ensure_metadata_in_output_dir")
    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    @patch("preprocess._convert_tiff_to_png", side_effect=_fake_tiff_to_png)
    @patch("preprocess.sys.platform", "win32")
    def test_run_ns_process_data_retry_preserves_sparse_layout_with_skip_colmap(
        self,
        _mock_convert,
        mock_run,
        _mock_which,
        _mock_ensure_metadata,
    ) -> None:
        """Retry with complete COLMAP should keep --skip-colmap and use staging root as --data."""
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
            source_image_name = "IMG_2105 .tif"
            (images_dir / source_image_name).write_text("fake image")
            for base_name in ("cameras", "images", "points3D"):
                (sparse_zero_dir / f"{base_name}.bin").write_bytes(b"ok")

            run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=True)

        self.assertEqual(mock_run.call_count, 2)
        first_command = mock_run.call_args_list[0].args[0]
        self.assertIn("--skip-colmap", first_command)
        first_colmap_index = first_command.index("--colmap-model-path") + 1
        self.assertEqual(Path(first_command[first_colmap_index]), input_dir / "sparse" / "0")

        second_command = mock_run.call_args_list[1].args[0]
        second_data_index = second_command.index("--data") + 1
        staged_root = Path(second_command[second_data_index])
        self.assertIn("ns_preprocess_staging_", str(staged_root))
        self.assertTrue((staged_root / "sparse" / "0").is_dir())
        self.assertTrue((staged_root / "images" / source_image_name).is_file())
        self.assertFalse((staged_root / "images" / "frame_000000.png").exists())
        self.assertEqual(Path(second_command[second_data_index]), staged_root)
        self.assertIn("--skip-colmap", second_command)
        second_colmap_index = second_command.index("--colmap-model-path") + 1
        self.assertEqual(Path(second_command[second_colmap_index]), staged_root / "sparse" / "0")
        self.assertNotEqual(Path(second_command[second_colmap_index]), input_dir / "sparse" / "0")
        _mock_convert.assert_not_called()

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

    @patch("preprocess.sys.platform", "win32")
    def test_prepare_windows_input_staging_preserves_original_names_when_colmap_is_complete(self) -> None:
        """When COLMAP sparse/0 is complete, staging must copy images 1:1 without rename/conversion."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            images_dir = input_dir / "images"
            sparse_zero = input_dir / "sparse" / "0"
            images_dir.mkdir(parents=True)
            sparse_zero.mkdir(parents=True)
            source_image_name = "IMG_2105 .tif"
            (images_dir / source_image_name).write_text("fake image")
            for base_name in ("cameras", "images", "points3D"):
                (sparse_zero / f"{base_name}.bin").write_bytes(b"ok")

            with patch("preprocess._convert_tiff_to_png") as mock_convert:
                staged_root = _prepare_windows_input_staging(
                    input_dir=input_dir,
                    process_input_dir=images_dir,
                    skip_colmap=True,
                )

            self.assertIn("ns_preprocess_staging_", staged_root.name)
            self.assertTrue((staged_root / "images" / source_image_name).is_file())
            self.assertFalse((staged_root / "images" / "frame_000000.png").exists())
            self.assertTrue((staged_root / "sparse" / "0").is_dir())
            mock_convert.assert_not_called()

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

    @patch("preprocess.which", return_value="C:/ffmpeg/bin/ffmpeg.exe")
    @patch("preprocess.subprocess.run")
    def test_run_ns_process_data_reports_clear_error_when_returncode_zero_but_missing_transforms(
        self,
        mock_run,
        _mock_which,
    ) -> None:
        """A successful exit code without transforms.json should raise a clear metadata error."""
        mock_completed = MagicMock()
        mock_completed.stdout = "INFO: not generating transforms.json because COLMAP is incomplete\n"
        mock_completed.stderr = ""
        mock_completed.returncode = 0
        mock_run.return_value = mock_completed

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = Path(tmp_dir) / "dataset"
            output_dir = Path(tmp_dir) / "out"
            input_dir.mkdir(parents=True)
            (input_dir / "frame_001.jpg").write_text("fake image")

            with self.assertRaises(FileNotFoundError) as ctx:
                run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=False)

        error_message = str(ctx.exception)
        self.assertIn("completed but transforms.json was not found", error_message)
        self.assertIn("not generated", error_message)

    @patch("preprocess.which", return_value=None)
    def test_ensure_ffmpeg_available_raises_clear_error_when_missing(self, _mock_which) -> None:
        with self.assertRaises(EnvironmentError) as ctx:
            _ensure_ffmpeg_available()

        self.assertIn("Could not find ffmpeg on PATH", str(ctx.exception))
        self.assertIn("ffmpeg.exe", str(ctx.exception))

    def test_rewrite_frame_file_paths_points_to_original_dataset_images(self) -> None:
        """Relative file paths should be rewritten to absolute paths in source dataset."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            source_image = input_dir / "images" / "frame_001.jpg"
            source_image.parent.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            source_image.write_text("fake jpg")

            transforms_data = {"frames": [{"file_path": "images/frame_001.jpg"}]}
            _rewrite_frame_file_paths_to_source_images(
                transforms_data=transforms_data,
                input_dir=input_dir,
                output_dir=output_dir,
            )

            rewritten_path = transforms_data["frames"][0]["file_path"]
            self.assertEqual(Path(rewritten_path), source_image.resolve())

    def test_save_transforms_json_persists_rewritten_file_path(self) -> None:
        """Updated transforms payload should be saved before split generation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            transforms_path = Path(tmp_dir) / "transforms.json"
            source_image = Path(tmp_dir) / "dataset" / "images" / "frame_001.jpg"
            source_image.parent.mkdir(parents=True)
            source_image.write_text("fake jpg")

            transforms_data = {"frames": [{"file_path": str(source_image.resolve())}]}
            save_transforms_json(transforms_path=transforms_path, transforms_data=transforms_data)

            payload = json.loads(transforms_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["frames"][0]["file_path"], str(source_image.resolve()))

    @patch("preprocess.write_blender_split_files")
    @patch("preprocess._create_png_companion_files")
    @patch("preprocess.save_transforms_json")
    @patch("preprocess._rewrite_frame_file_paths_to_source_images")
    @patch("preprocess.load_transforms_json")
    @patch("preprocess.run_ns_process_data")
    def test_preprocess_dataset_does_not_create_output_images_directory(
        self,
        mock_run_ns_process_data,
        mock_load_transforms,
        mock_rewrite,
        mock_save_transforms,
        mock_create_companion,
        mock_write_splits,
    ) -> None:
        """Preprocessing should only update JSON metadata and never copy images into run output."""
        mock_load_transforms.return_value = {"frames": []}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_dir = root / "dataset"
            output_dir = root / "run" / "preprocessed_dataset"
            (input_dir / "images").mkdir(parents=True)
            (input_dir / "images" / "frame_001.jpg").write_text("fake image")

            preprocess_dataset(input_dir=input_dir, output_dir=output_dir, skip_colmap_flag=False)

            self.assertFalse((output_dir / "images").exists())
            mock_run_ns_process_data.assert_called_once()
            mock_rewrite.assert_called_once()
            mock_save_transforms.assert_called_once()
            mock_create_companion.assert_called_once()
            mock_write_splits.assert_called_once()

    @patch("preprocess._convert_image_to_png", side_effect=_fake_image_to_png)
    def test_create_png_companion_files_creates_file_path_png_companions(self, _mock_convert) -> None:
        """Each absolute frame path should get a `<file_path>.png` companion beside source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_frame = Path(tmp_dir) / "dataset" / "images" / "IMG_2088.tif"
            source_frame.parent.mkdir(parents=True)
            source_frame.write_bytes(b"fake tif")

            transforms_data = {
                "frames": [
                    {"file_path": str(source_frame.resolve())},
                ]
            }

            _create_png_companion_files(transforms_data=transforms_data)

            self.assertTrue(Path(f"{source_frame.resolve()}.png").is_file())

    def test_create_png_companion_files_skips_missing_source_without_crashing(self) -> None:
        """Missing source frame files should be logged and ignored without raising errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_frame = Path(tmp_dir) / "dataset" / "images" / "missing_frame.tif"
            transforms_data = {
                "frames": [
                    {"file_path": str(missing_frame)},
                ]
            }

            with self.assertLogs("preprocess", level="WARNING") as captured_logs:
                _create_png_companion_files(transforms_data=transforms_data)

            self.assertIn("Source frame missing for PNG companion creation", "\n".join(captured_logs.output))
            self.assertFalse(Path(f"{missing_frame}.png").exists())


