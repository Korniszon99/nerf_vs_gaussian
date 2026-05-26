#!/usr/bin/env python
"""Quick test to verify transforms.json copying fix works."""

import json
import tempfile
from pathlib import Path

# Test the _ensure_metadata_in_output_dir function
from preprocess import _ensure_metadata_in_output_dir, NERFSTUDIO_TRANSFORMS_FILE


def test_ensure_metadata_copies_from_source_dir():
    """Test that transforms.json is copied from source to output."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create source dir with transforms.json
        source_dir = Path(tmp_dir) / "source"
        source_dir.mkdir(parents=True)

        transforms_data = {
            "frames": [{"file_path": f"frame_{i:03d}.png"} for i in range(10)],
            "camera_angle_x": 0.5,
        }
        source_transforms = source_dir / NERFSTUDIO_TRANSFORMS_FILE
        source_transforms.write_text(json.dumps(transforms_data))

        # Create output dir (empty)
        output_dir = Path(tmp_dir) / "output"
        output_dir.mkdir(parents=True)

        # Call the function
        _ensure_metadata_in_output_dir(output_dir, source_dir)

        # Verify transforms.json was copied
        output_transforms = output_dir / NERFSTUDIO_TRANSFORMS_FILE
        assert output_transforms.is_file(), f"Expected {output_transforms} to exist"

        # Verify content matches
        loaded = json.loads(output_transforms.read_text())
        assert loaded == transforms_data, "Content mismatch"
        print("✓ Test passed: transforms.json correctly copied from source to output")


def test_ensure_metadata_checks_parent_dir():
    """Test that transforms.json is found in parent directory when needed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create parent dir with transforms.json
        parent_dir = Path(tmp_dir) / "parent"
        parent_dir.mkdir(parents=True)

        transforms_data = {"frames": [], "test": True}
        parent_transforms = parent_dir / NERFSTUDIO_TRANSFORMS_FILE
        parent_transforms.write_text(json.dumps(transforms_data))

        # Create nested source dir (like staging/images)
        source_dir = parent_dir / "images"
        source_dir.mkdir(parents=True)

        # Create output dir
        output_dir = Path(tmp_dir) / "output"
        output_dir.mkdir(parents=True)

        # Call the function with nested source dir
        _ensure_metadata_in_output_dir(output_dir, source_dir)

        # Verify transforms.json was copied
        output_transforms = output_dir / NERFSTUDIO_TRANSFORMS_FILE
        assert output_transforms.is_file(), f"Expected {output_transforms} to exist"

        loaded = json.loads(output_transforms.read_text())
        assert loaded == transforms_data, "Content mismatch"
        print("✓ Test passed: transforms.json correctly found in parent directory")


def test_ensure_metadata_handles_existing_file():
    """Test that existing transforms.json is not overwritten."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create output dir with existing transforms.json
        output_dir = Path(tmp_dir) / "output"
        output_dir.mkdir(parents=True)

        existing_data = {"existing": True, "frames": []}
        output_transforms = output_dir / NERFSTUDIO_TRANSFORMS_FILE
        output_transforms.write_text(json.dumps(existing_data))

        # Create source dir (which shouldn't be used)
        source_dir = Path(tmp_dir) / "source"
        source_dir.mkdir(parents=True)

        # Call the function
        _ensure_metadata_in_output_dir(output_dir, source_dir)

        # Verify original file wasn't modified
        loaded = json.loads(output_transforms.read_text())
        assert loaded == existing_data, "Existing file was modified"
        print("✓ Test passed: existing transforms.json not overwritten")


if __name__ == "__main__":
    test_ensure_metadata_copies_from_source_dir()
    test_ensure_metadata_checks_parent_dir()
    test_ensure_metadata_handles_existing_file()
    print("\n✓✓✓ All tests passed! Fix is working correctly.")

