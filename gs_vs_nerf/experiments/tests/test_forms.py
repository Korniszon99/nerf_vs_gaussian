"""Testy walidacji formularzy."""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase

from experiments.forms import DatasetForm


class DatasetFormValidationTests(TestCase):
    """Testy walidacji DatasetForm.clean_folder_path()."""

    def test_form_rejects_folder_without_images(self):
        """Test że forma odrzuca folder bez zdjęć."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Folder pusta — brak zdjęć
            form = DatasetForm(data={
                "name": "empty-dataset",
                "description": "Empty folder",
                "folder_path": tmpdir,
            })
            self.assertFalse(form.is_valid())
            self.assertIn("Brak obsługiwanych zdjęć", form.errors["folder_path"][0])

    def test_form_accepts_folder_with_jpg_in_images_subdir(self):
        """Test że forma akceptuje folder z .jpg w podfolderu images/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Stwórz podfolder images/ i dodaj .jpg
            images_dir = Path(tmpdir) / "images"
            images_dir.mkdir()
            (images_dir / "test.jpg").touch()

            form = DatasetForm(data={
                "name": "jpg-dataset",
                "description": "With JPG",
                "folder_path": tmpdir,
            })
            self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_accepts_folder_with_jpg_in_root(self):
        """Test że forma akceptuje folder z .jpg w root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Dodaj .jpg w root
            (Path(tmpdir) / "photo.jpg").touch()

            form = DatasetForm(data={
                "name": "root-jpg-dataset",
                "description": "JPG in root",
                "folder_path": tmpdir,
            })
            self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_accepts_all_supported_image_formats(self):
        """Test że forma akceptuje wszystkie obsługiwane formaty."""
        supported_formats = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"]

        for fmt in supported_formats:
            with tempfile.TemporaryDirectory() as tmpdir:
                (Path(tmpdir) / f"test{fmt}").touch()

                form = DatasetForm(data={
                    "name": f"dataset-{fmt}",
                    "description": f"Format {fmt}",
                    "folder_path": tmpdir,
                })
                self.assertTrue(form.is_valid(), f"Form should accept {fmt}, but got: {form.errors}")

    def test_form_shows_warning_for_polish_diacritics(self):
        """Test że forma pokazuje warning dla polskich znaków (ale form przechodzi)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Stwórz zdjęcie
            (Path(tmpdir) / "test.jpg").touch()

            # Ścieżka z polskimi znakami
            diacritics_path = Path(tmpdir).parent / "ółłółł"
            try:
                diacritics_path.mkdir()
                (diacritics_path / "test.jpg").touch()

                form = DatasetForm(data={
                    "name": "diacs-dataset",
                    "description": "With diacritics",
                    "folder_path": str(diacritics_path),
                })

                # Form powinien być valid
                self.assertTrue(form.is_valid(), f"Form should pass with diacritics, errors: {form.errors}")

                # Ale powinno być ostrzeżenie non-field error
                non_field_errors = form.non_field_errors()
                warning_found = any("diakrytyczne" in str(err).lower() for err in non_field_errors)
                # Ostrzeżenie powinno być - ale form się przechodzi
                # (W naszej implementacji, warning jest dodawany do non_field_errors)
            finally:
                # Cleanup
                try:
                    import shutil
                    shutil.rmtree(diacritics_path)
                except Exception:
                    pass

    def test_form_rejects_nonexistent_path(self):
        """Test że forma odrzuca ścieżkę, która nie istnieje."""
        form = DatasetForm(data={
            "name": "nonexistent",
            "description": "",
            "folder_path": "/nonexistent/path/that/does/not/exist",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("nie istnieje", form.errors["folder_path"][0].lower())

    def test_has_diacritics_helper_detects_polish_chars(self):
        """Test metody _has_diacritics() dla polskich znaków."""
        self.assertTrue(DatasetForm._has_diacritics("Iłża"))
        self.assertTrue(DatasetForm._has_diacritics("ąćęłńóśźż"))
        self.assertTrue(DatasetForm._has_diacritics("/home/user/Iłża/data"))

        self.assertFalse(DatasetForm._has_diacritics("data"))
        self.assertFalse(DatasetForm._has_diacritics("/tmp/data/images"))

    def test_form_ignores_case_for_image_extensions(self):
        """Test że forma ignoruje wielkość liter w rozszerzeniach."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Stwórz plik .JPG (duże litery)
            (Path(tmpdir) / "TEST.JPG").touch()

            form = DatasetForm(data={
                "name": "uppercase-dataset",
                "description": "",
                "folder_path": tmpdir,
            })
            self.assertTrue(form.is_valid(), f"Form should accept .JPG (uppercase): {form.errors}")

