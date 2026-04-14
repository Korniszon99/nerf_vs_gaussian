"""Testy service'u importu zdjęć."""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase

from experiments.models import Dataset, ImageFrame
from experiments.services.dataset_import import import_images_from_folder


class DatasetImportServiceTests(TestCase):
    """Testy automatycznego importu zdjęć z folderu."""

    def test_import_images_from_folder_with_valid_path(self) -> None:
        """Test: import zdjęć ze spójnym folderem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Utwórz test folder ze zdjęciami
            images_dir = Path(tmpdir) / "images"
            images_dir.mkdir()

            # Utwórz test zdjęcia
            (images_dir / "IMG_0001.jpg").touch()
            (images_dir / "IMG_0002.jpg").touch()
            (images_dir / "IMG_0010.jpg").touch()  # Naturalne sortowanie: powinno być po 0002

            # Utwórz dataset
            dataset = Dataset.objects.create(name="test_dataset", data_path=str(Path(tmpdir)))

            # Importuj
            result = import_images_from_folder(dataset)

            # Asercje
            self.assertEqual(result["imported"], 3)
            self.assertEqual(len(result["skipped"]), 0)
            self.assertEqual(len(result["errors"]), 0)

            # Sprawdź, czy zdjęcia mają prawidłowe indeksy
            images = dataset.images.order_by("frame_index")
            self.assertEqual(images.count(), 3)
            self.assertEqual(list(images.values_list("frame_index", flat=True)), [0, 1, 2])

    def test_import_images_natural_sorting(self) -> None:
        """Test: naturalne sortowanie nazw (IMG_2 < IMG_10)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            images_dir = Path(tmpdir) / "images"
            images_dir.mkdir()

            # Utwórz zdjęcia w nieprzypadkowej kolejności
            (images_dir / "IMG_10.jpg").touch()
            (images_dir / "IMG_2.jpg").touch()
            (images_dir / "IMG_1.jpg").touch()

            dataset = Dataset.objects.create(name="test_natural_sort", data_path=str(Path(tmpdir)))
            result = import_images_from_folder(dataset)

            self.assertEqual(result["imported"], 3)

            # Sprawdź, czy są posortowane naturalnie
            images = dataset.images.order_by("frame_index")
            names = [Path(img.image_file.name).name for img in images]
            self.assertEqual(names, ["IMG_1.jpg", "IMG_2.jpg", "IMG_10.jpg"])

    def test_import_images_skip_duplicates(self) -> None:
        """Test: pomijanie duplikatów."""
        with tempfile.TemporaryDirectory() as tmpdir:
            images_dir = Path(tmpdir) / "images"
            images_dir.mkdir()

            (images_dir / "IMG_0001.jpg").touch()
            (images_dir / "IMG_0002.jpg").touch()

            dataset = Dataset.objects.create(name="test_duplicates", data_path=str(Path(tmpdir)))

            # Pierwszy import
            result1 = import_images_from_folder(dataset)
            self.assertEqual(result1["imported"], 2)

            # Drugi import (powinny być pominięte)
            result2 = import_images_from_folder(dataset)
            self.assertEqual(result2["imported"], 0)
            self.assertEqual(len(result2["skipped"]), 2)

    def test_import_images_nonexistent_path(self) -> None:
        """Test: ścieżka nie istnieje."""
        dataset = Dataset.objects.create(name="test_nonexistent", data_path="/nonexistent/path")
        result = import_images_from_folder(dataset)

        self.assertEqual(result["imported"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("nie istnieje", result["errors"][0].lower())

    def test_import_images_empty_folder(self) -> None:
        """Test: pusty folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset = Dataset.objects.create(name="test_empty", data_path=str(Path(tmpdir)))
            result = import_images_from_folder(dataset)

            self.assertEqual(result["imported"], 0)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("brak", result["errors"][0].lower())

