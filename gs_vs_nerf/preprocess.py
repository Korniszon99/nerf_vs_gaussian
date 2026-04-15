from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from typing import Any

NERFSTUDIO_TRANSFORMS_FILE = "transforms.json"
BLENDER_SPLIT_FILES = ("transforms_train.json", "transforms_test.json", "transforms_val.json")
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".exr"}
TIFF_IMAGE_EXTENSIONS = {".tif", ".tiff"}

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for dataset preprocessing.

    Returns:
        Parsed command-line arguments including input/output directories and
        optional COLMAP skipping behavior.
    """
    parser = argparse.ArgumentParser(description="Prepare Nerfstudio metadata for training pipelines.")
    parser.add_argument("--input-dir", required=True, help="Path to raw dataset directory.")
    parser.add_argument("--output-dir", required=True, help="Path to processed dataset output directory.")
    parser.add_argument(
        "--skip-colmap",
        action="store_true",
        help="Skip COLMAP stage when running ns-process-data images.",
    )
    return parser.parse_args()


def main() -> int:
    """Run preprocessing pipeline and return shell exit status.

    Returns:
        0 on success, otherwise 1 with an error message printed to stderr.
    """
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="[preprocess] %(levelname)s: %(message)s")
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    try:
        preprocess_dataset(input_dir=input_dir, output_dir=output_dir, skip_colmap_flag=args.skip_colmap)
    except Exception as exc:
        print(f"[preprocess] ERROR: {exc}", file=sys.stderr)
        return 1

    # Keep machine-readable stdout output for the runner contract.
    print(json.dumps({"status": "success", "output_dir": str(output_dir)}))
    return 0


def preprocess_dataset(input_dir: Path, output_dir: Path, skip_colmap_flag: bool) -> None:
    """Generate Nerfstudio and Blender metadata files from an input dataset.

    Args:
        input_dir: Source dataset directory containing raw images (and optionally sparse/0).
        output_dir: Destination directory where processed data and JSON metadata are written.
        skip_colmap_flag: Explicit user flag to skip COLMAP in ns-process-data.
    """
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"Input directory is invalid: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    skip_colmap = should_skip_colmap(input_dir=input_dir, skip_colmap_flag=skip_colmap_flag)
    run_ns_process_data(input_dir=input_dir, output_dir=output_dir, skip_colmap=skip_colmap)

    transforms_path = output_dir / NERFSTUDIO_TRANSFORMS_FILE
    transforms_data = load_transforms_json(transforms_path)
    write_blender_split_files(transforms_data=transforms_data, output_dir=output_dir)


def should_skip_colmap(input_dir: Path, skip_colmap_flag: bool) -> bool:
    """Determine whether COLMAP should be skipped for ns-process-data.

    Args:
        input_dir: Source dataset directory to inspect for sparse/0 layout.
        skip_colmap_flag: User-provided override from CLI.

    Returns:
        True if COLMAP should be skipped.
    """
    if skip_colmap_flag:
        return True
    return (input_dir / "sparse" / "0").is_dir()


def run_ns_process_data(input_dir: Path, output_dir: Path, skip_colmap: bool) -> None:
    """Run ns-process-data images to create transforms.json metadata.

    Args:
        input_dir: Directory with raw images.
        output_dir: Directory where processed output is generated.
        skip_colmap: Whether to pass --skip-colmap to the command.
    """
    _ensure_ffmpeg_available()

    process_input_dir = _resolve_ns_process_data_input_dir(input_dir)
    command = [
        "ns-process-data",
        "images",
        "--data",
        str(process_input_dir),
        "--output-dir",
        str(output_dir),
    ]
    if skip_colmap:
        command.append("--skip-colmap")
    if _should_disable_fast_image_processing(input_dir=input_dir):
        command.append("--no-same-dimensions")

    logger.info("Running: %s", subprocess.list2cmdline(command))
    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    retried_input_dir: Path | None = None
    last_attempt_input_dir = process_input_dir
    if completed.returncode != 0 and _can_retry_with_windows_staging(process_input_dir):
        retried_input_dir = _prepare_windows_input_staging(
            input_dir=input_dir,
            process_input_dir=process_input_dir,
            skip_colmap=skip_colmap,
        )
        if retried_input_dir != process_input_dir:
            retry_command = _replace_data_arg(command, retried_input_dir)
            logger.warning(
                "ns-process-data failed on initial input. Retrying with sanitized staging directory: %s",
                retried_input_dir,
            )
            logger.info("Retry command: %s", subprocess.list2cmdline(retry_command))
            completed = subprocess.run(retry_command, text=True, capture_output=True, check=False)
            last_attempt_input_dir = retried_input_dir

            if completed.returncode != 0 and _can_retry_with_staging_root(retried_input_dir):
                staging_root = retried_input_dir.parent
                root_retry_command = _replace_data_arg(command, staging_root)
                logger.warning(
                    "Retry on staged images directory failed. Retrying once with staging root: %s",
                    staging_root,
                )
                logger.info("Root retry command: %s", subprocess.list2cmdline(root_retry_command))
                completed = subprocess.run(root_retry_command, text=True, capture_output=True, check=False)
                last_attempt_input_dir = staging_root

    if (
        completed.returncode != 0
        and sys.platform.startswith("win")
        and _looks_like_ffmpeg_processing_failure(completed)
    ):
        skip_processing_command = _with_skip_image_processing_flag(
            _replace_data_arg(command, last_attempt_input_dir)
        )
        logger.warning(
            "Detected ffmpeg processing failure on Windows. Retrying once with --skip-image-processing."
        )
        logger.info("Skip-image-processing retry command: %s", subprocess.list2cmdline(skip_processing_command))
        completed = subprocess.run(skip_processing_command, text=True, capture_output=True, check=False)

    if completed.stdout.strip():
        logger.info("ns-process-data output:\n%s", completed.stdout.strip())
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        stdout_text = completed.stdout.strip()
        details = stderr_text or stdout_text or "no stdout/stderr captured"
        if stderr_text and stdout_text and stdout_text != stderr_text:
            details = f"stderr: {stderr_text}; stdout: {stdout_text}"
        if retried_input_dir is not None:
            details = f"{details}. Retry input directory: {last_attempt_input_dir}"
        raise RuntimeError(
            "ns-process-data images failed with "
            f"exit code {completed.returncode}. Details: {details}"
        )

    logger.info("transforms.json generation completed.")


def _ensure_ffmpeg_available() -> None:
    """Fail fast with a Windows-friendly diagnostic when ffmpeg is missing from PATH."""
    if which("ffmpeg") or which("ffmpeg.exe"):
        return

    path_value = os.environ.get("PATH", "")
    path_entries = path_value.split(os.pathsep) if path_value else []
    path_preview = os.pathsep.join(path_entries[:5]) if path_entries else "<empty>"
    raise EnvironmentError(
        "Could not find ffmpeg on PATH. Install ffmpeg and make sure the directory containing "
        f"ffmpeg.exe is available to the Python process. Current PATH preview: {path_preview}"
    )


def _resolve_ns_process_data_input_dir(input_dir: Path) -> Path:
    """Pick the most specific image directory for ns-process-data.

    If the dataset follows the common ``dataset/images/`` layout and that folder
    contains images, pass that directory to ``ns-process-data``. Otherwise fall
    back to the dataset root so root-level image datasets still work.

    When a COLMAP layout is present at ``sparse/0``, keep the dataset root so
    ``ns-process-data`` can still see the reconstruction metadata instead of
    hiding it behind the ``images/`` subdirectory.
    """
    if (input_dir / "sparse" / "0").is_dir():
        return input_dir

    images_dir = input_dir / "images"
    if images_dir.is_dir() and any(
        child.is_file() and child.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS for child in images_dir.iterdir()
    ):
        return images_dir
    return input_dir


def _should_disable_fast_image_processing(input_dir: Path) -> bool:
    """Return True when TIFF datasets on Windows should avoid the fast ffmpeg path."""
    if not sys.platform.startswith("win"):
        return False
    return _contains_tiff_images(input_dir)


def _contains_tiff_images(input_dir: Path) -> bool:
    """Return True if TIFF images exist in the dataset root or images/ subdirectory."""
    candidate_dirs = []
    images_dir = input_dir / "images"
    if images_dir.is_dir():
        candidate_dirs.append(images_dir)
    if input_dir.is_dir():
        candidate_dirs.append(input_dir)

    seen: set[Path] = set()
    for candidate_dir in candidate_dirs:
        if candidate_dir in seen:
            continue
        seen.add(candidate_dir)
        for child in candidate_dir.iterdir():
            if child.is_file() and child.suffix.lower() in TIFF_IMAGE_EXTENSIONS:
                return True
    return False


def _prepare_windows_input_staging(
    input_dir: Path,
    process_input_dir: Path,
    skip_colmap: bool,
) -> Path:
    """Create a sanitized staging dataset on Windows when TIFF or unsafe file names are detected.

    The staging root is created in the OS temp directory to avoid nested input/output
    interactions during retry runs and to keep Windows paths shorter.
    """
    if not sys.platform.startswith("win"):
        return process_input_dir

    image_dir = _resolve_image_directory(process_input_dir)
    image_files = _list_supported_images(image_dir)
    if not image_files:
        return process_input_dir

    requires_staging = _contains_tiff_images(image_dir) or _has_unsafe_image_names(image_files)
    if not requires_staging:
        return process_input_dir

    staging_root = _create_windows_staging_root()

    destination_images_dir = staging_root / "images"
    destination_images_dir.mkdir(parents=True, exist_ok=True)

    for index, source_file in enumerate(image_files):
        _stage_windows_image(source_file=source_file, destination_images_dir=destination_images_dir, index=index)

    if skip_colmap and (input_dir / "sparse" / "0").is_dir():
        source_sparse = input_dir / "sparse"
        destination_sparse = staging_root / "sparse"
        shutil.copytree(source_sparse, destination_sparse, dirs_exist_ok=True)

    logger.info(
        "Using Windows staging input with sanitized image names: %s (copied %d files)",
        staging_root,
        len(image_files),
    )

    if skip_colmap and (staging_root / "sparse" / "0").is_dir():
        return staging_root
    return destination_images_dir


def _create_windows_staging_root() -> Path:
    """Create and return a writable staging root for Windows retry preprocessing."""
    try:
        return Path(tempfile.mkdtemp(prefix="ns_preprocess_staging_"))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not create temporary staging directory via tempfile.mkdtemp: %s. "
            "Falling back to current working directory.",
            exc,
        )
        fallback_root = Path.cwd() / "_preprocess_staging"
        if fallback_root.exists():
            shutil.rmtree(fallback_root)
        fallback_root.mkdir(parents=True, exist_ok=True)
        return fallback_root


def _resolve_image_directory(process_input_dir: Path) -> Path:
    """Return the directory that directly contains image files for preprocessing."""
    nested_images_dir = process_input_dir / "images"
    if nested_images_dir.is_dir():
        return nested_images_dir
    return process_input_dir


def _stage_windows_image(source_file: Path, destination_images_dir: Path, index: int) -> Path:
    """Copy one image into staging using a deterministic safe filename.

    TIFF images are converted to PNG when Pillow is available to avoid ffmpeg
    decode issues on some Windows builds.
    """
    source_suffix = source_file.suffix.lower()
    if source_suffix in TIFF_IMAGE_EXTENSIONS:
        png_destination = destination_images_dir / f"frame_{index:06d}.png"
        if _convert_tiff_to_png(source_file=source_file, destination_file=png_destination):
            return png_destination

        fallback_destination = destination_images_dir / f"frame_{index:06d}{source_suffix}"
        shutil.copy2(source_file, fallback_destination)
        logger.warning(
            "Could not convert TIFF to PNG for staging (%s). Falling back to copied TIFF: %s",
            source_file,
            fallback_destination,
        )
        return fallback_destination

    normalized_ext = source_suffix or ".png"
    destination_file = destination_images_dir / f"frame_{index:06d}{normalized_ext}"
    shutil.copy2(source_file, destination_file)
    return destination_file


def _convert_tiff_to_png(source_file: Path, destination_file: Path) -> bool:
    """Convert a TIFF image to PNG using Pillow when available."""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "Pillow is not installed, cannot convert TIFF to PNG during staging: %s",
            source_file,
        )
        return False

    try:
        with Image.open(source_file) as image:
            image.save(destination_file, format="PNG")
    except Exception as exc:  # noqa: BLE001
        logger.warning("TIFF to PNG conversion failed for %s: %s", source_file, exc)
        return False

    return True


def _list_supported_images(image_dir: Path) -> list[Path]:
    """Return supported image files in deterministic order."""
    if not image_dir.is_dir():
        return []

    files = [
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    return sorted(files, key=lambda path: path.name.lower())


def _has_unsafe_image_names(image_files: list[Path]) -> bool:
    """Return True for names likely to break ffmpeg parsing on Windows pipelines."""
    for image_file in image_files:
        name = image_file.name
        if name != name.strip() or any(char.isspace() for char in name):
            return True
    return False


def _can_retry_with_windows_staging(process_input_dir: Path) -> bool:
    """Return True when Windows image input can be retried via a sanitized staging directory."""
    if not sys.platform.startswith("win"):
        return False

    image_dir = _resolve_image_directory(process_input_dir)
    image_files = _list_supported_images(image_dir)
    if not image_files:
        return False

    return _contains_tiff_images(image_dir) or _has_unsafe_image_names(image_files)


def _replace_data_arg(command: list[str], data_dir: Path) -> list[str]:
    """Return a command copy with the --data argument updated to a new directory."""
    if "--data" not in command:
        return command[:]

    index = command.index("--data") + 1
    updated = command[:]
    if index < len(updated):
        updated[index] = str(data_dir)
    return updated


def _with_skip_image_processing_flag(command: list[str]) -> list[str]:
    """Return command copy with `--skip-image-processing` appended when absent."""
    if "--skip-image-processing" in command:
        return command[:]
    return [*command, "--skip-image-processing"]


def _looks_like_ffmpeg_processing_failure(completed: subprocess.CompletedProcess[str]) -> bool:
    """Return True when ns-process-data output indicates an ffmpeg command failure."""
    stderr_text = completed.stderr or ""
    stdout_text = completed.stdout or ""
    failure_output = (stderr_text + "\n" + stdout_text).lower()
    return "error running command: ffmpeg" in failure_output


def _can_retry_with_staging_root(retried_input_dir: Path) -> bool:
    """Return True when a Windows retry used a staging `images` directory.

    In that case, a final retry with the staging root can avoid ffmpeg issues
    observed on some Windows setups for `.../images` input paths.
    """
    if not sys.platform.startswith("win"):
        return False

    parent_name = retried_input_dir.parent.name.lower()
    is_staging_parent = parent_name.startswith("ns_preprocess_staging_") or parent_name == "_preprocess_staging"
    return retried_input_dir.name.lower() == "images" and is_staging_parent


def load_transforms_json(transforms_path: Path) -> dict[str, Any]:
    """Load and validate transforms.json produced by ns-process-data.

    Args:
        transforms_path: Path to transforms.json in output directory.

    Returns:
        Parsed transforms object.
    """
    if not transforms_path.is_file():
        raise FileNotFoundError(f"Expected metadata file not found: {transforms_path}")

    transforms_data = json.loads(transforms_path.read_text(encoding="utf-8"))
    frames = transforms_data.get("frames")
    if not isinstance(frames, list):
        raise ValueError(f"Invalid transforms.json format: 'frames' must be a list in {transforms_path}")

    logger.info("Loaded %d frames from %s.", len(frames), transforms_path.name)
    return transforms_data


def split_frames(frames: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split frames into train/test/val partitions using 80/10/10 order.

    Args:
        frames: Frame entries from transforms.json.

    Returns:
        Tuple of (train_frames, test_frames, val_frames).
    """
    total = len(frames)
    train_end = int(total * 0.8)
    test_end = train_end + int(total * 0.1)
    return frames[:train_end], frames[train_end:test_end], frames[test_end:]


def build_split_payload(base_metadata: dict[str, Any], split_frames_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Create split JSON payload preserving top-level metadata fields.

    Args:
        base_metadata: Original transforms.json without frame overrides.
        split_frames_data: Frame subset for one split file.

    Returns:
        Metadata dictionary with preserved top-level fields and split frames.
    """
    payload = dict(base_metadata)
    payload["frames"] = split_frames_data
    return payload


def write_blender_split_files(transforms_data: dict[str, Any], output_dir: Path) -> None:
    """Write Blender-style split metadata files from transforms.json content.

    Args:
        transforms_data: Parsed transforms.json object.
        output_dir: Destination directory for split JSON files.
    """
    all_frames = transforms_data.get("frames", [])
    if not isinstance(all_frames, list):
        raise ValueError("Cannot create split files: transforms.json frames are invalid.")

    train_frames, test_frames, val_frames = split_frames(all_frames)
    base_metadata = {key: value for key, value in transforms_data.items() if key != "frames"}

    split_map = {
        BLENDER_SPLIT_FILES[0]: train_frames,
        BLENDER_SPLIT_FILES[1]: test_frames,
        BLENDER_SPLIT_FILES[2]: val_frames,
    }

    for file_name, split_data in split_map.items():
        payload = build_split_payload(base_metadata=base_metadata, split_frames_data=split_data)
        split_path = output_dir / file_name
        split_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Wrote %s (%d frames).", file_name, len(split_data))


if __name__ == "__main__":
    raise SystemExit(main())
