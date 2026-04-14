"""Service do automatycznego importu zdjęć z folderu datasetu."""

from __future__ import annotations

import logging
from pathlib import Path

from experiments.models import Dataset, ImageFrame

logger = logging.getLogger(__name__)

# Obsługiwane rozszerzenia obrazów
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}


def import_images_from_folder(dataset: Dataset) -> dict[str, int | list[str]]:
    """
    Skanuje folder data_path i importuje zdjęcia z auto-indeksem.

    Args:
        dataset: Dataset do uzupełnienia

    Returns:
        dict z kluczami:
        - "imported": liczba zaimportowanych zdjęć
        - "skipped": lista plików, które pominięto (duplikaty, nieznane rozszerzenia)
        - "errors": lista błędów podczas importu
    """
    from django.db.models import Max

    data_path = Path(dataset.data_path)

    if not data_path.exists():
        logger.error(f"Ścieżka datasetu nie istnieje: {data_path}")
        return {"imported": 0, "skipped": [], "errors": [f"Ścieżka nie istnieje: {data_path}"]}

    if not data_path.is_dir():
        logger.error(f"data_path nie jest katalogiem: {data_path}")
        return {"imported": 0, "skipped": [], "errors": [f"Nie jest katalogiem: {data_path}"]}

    # Szukaj zdjęć w katalogach images/, albo w root folderu
    images_dir = data_path / "images"
    if images_dir.exists() and images_dir.is_dir():
        search_dir = images_dir
    else:
        search_dir = data_path

    logger.info(f"Skanuję folder: {search_dir}")

    # Zbierz wszystkie zdjęcia i sortuj naturalnie
    image_files = sorted(
        (p for p in search_dir.glob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda x: _natural_sort_key(x.name),
    )

    if not image_files:
        logger.warning(f"Brak zdjęć w: {search_dir}")
        return {"imported": 0, "skipped": [], "errors": [f"Brak zdjęć w katalogu: {search_dir}"]}

    imported = 0
    skipped = []
    errors = []

    # Pobierz aktualny maksymalny indeks
    max_index = dataset.images.aggregate(max_idx=Max("frame_index"))["max_idx"]
    next_index = (max_index or -1) + 1

    for image_path in image_files:
        try:
            # Sprawdź, czy już istnieje
            if ImageFrame.objects.filter(dataset=dataset, image_file=str(image_path)).exists():
                skipped.append(f"{image_path.name} (już istnieje)")
                continue

            # Utwórz ImageFrame
            frame = ImageFrame(
                dataset=dataset,
                frame_index=next_index,
            )
            # Ustaw image_file jako relatywną ścieżkę lub nazwę pliku
            frame.image_file.name = str(image_path)
            frame.save()

            logger.info(f"Zaimportowano: {image_path.name} (indeks: {next_index})")
            imported += 1
            next_index += 1

        except Exception as exc:
            error_msg = f"{image_path.name}: {str(exc)}"
            errors.append(error_msg)
            logger.error(error_msg, exc_info=True)

    logger.info(f"Import zakończony: {imported} zaimportowane, {len(skipped)} pominięte, {len(errors)} błędy")
    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


def _natural_sort_key(filename: str) -> tuple:
    """Zwraca klucz do naturalnego sortowania nazw plików (IMG_2 < IMG_10)."""
    import re

    parts = []
    for part in re.split(r"(\d+)", filename):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part.lower())
    return tuple(parts)

