from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

NERFSTUDIO_TRANSFORMS_FILE = "transforms.json"
BLENDER_SPLIT_FILES = ("transforms_train.json", "transforms_test.json", "transforms_val.json")


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
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    try:
        preprocess_dataset(input_dir=input_dir, output_dir=output_dir, skip_colmap_flag=args.skip_colmap)
    except Exception as exc:
        print(f"[preprocess] ERROR: {exc}", file=sys.stderr)
        return 1

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
    command = [
        "ns-process-data",
        "images",
        "--data",
        str(input_dir),
        "--output-dir",
        str(output_dir),
    ]
    if skip_colmap:
        command.append("--skip-colmap")

    print(f"[preprocess] Running: {subprocess.list2cmdline(command)}")
    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    if completed.stdout.strip():
        print("[preprocess] ns-process-data output:")
        print(completed.stdout.strip())
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip() or "no stderr captured"
        raise RuntimeError(
            "ns-process-data images failed with "
            f"exit code {completed.returncode}. Details: {stderr_text}"
        )

    print("[preprocess] transforms.json generation completed.")


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

    print(f"[preprocess] Loaded {len(frames)} frames from {transforms_path.name}.")
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
        print(f"[preprocess] Wrote {file_name} ({len(split_data)} frames).")


if __name__ == "__main__":
    raise SystemExit(main())
