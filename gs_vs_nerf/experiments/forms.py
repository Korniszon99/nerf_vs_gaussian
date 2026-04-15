import json

from django import forms

from .models import CameraPose, Dataset, ExperimentRun, ImageFrame


class DatasetForm(forms.ModelForm):
    folder_path = forms.CharField(
        required=True,
        label="Ścieżka do folderu datasetu",
        widget=forms.TextInput(attrs={
            "type": "text",
            "placeholder": "C:\\Users\\..\\data\\ilza lub /path/to/ilza",
            "class": "form-control",
        }),
        help_text="Wpisz absolutną ścieżkę do folderu zawierającego zdjęcia (lub sparse/0 dla COLMAP).",
    )

    class Meta:
        model = Dataset
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.data_path:
            self.fields["folder_path"].initial = self.instance.data_path

    def clean_folder_path(self):
        import unicodedata
        from pathlib import Path

        folder_str = self.cleaned_data.get("folder_path", "").strip()
        if not folder_str:
            raise forms.ValidationError("Ścieżka nie może być pusta.")

        path = Path(folder_str)
        if not path.exists():
            raise forms.ValidationError(f"Ścieżka nie istnieje: {path}")
        if not path.is_dir():
            raise forms.ValidationError(f"Ścieżka nie jest katalogiem: {path}")

        # Sprawdź czy folder zawiera obsługiwane zdjęcia
        supported_extensions = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}

        # Szukaj w images/ najpierw, potem w root
        images_dir = path / "images"
        if images_dir.exists() and images_dir.is_dir():
            search_dir = images_dir
        else:
            search_dir = path

        # Wyszukaj zdjęcia
        image_files = [
            f for f in search_dir.iterdir()
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]

        if not image_files:
            search_location = f"{path}/images/ lub {path}"
            raise forms.ValidationError(
                f"Brak obsługiwanych zdjęć w {search_location}. "
                f"Obsługiwane formaty: {', '.join(sorted(supported_extensions))}"
            )

        # Ostrzeżenie o znakach diakrytycznych (ale form przechodzi)
        if self._has_diacritics(folder_str):
            self.add_error(None, forms.ValidationError(
                "⚠️ Ścieżka zawiera znaki diakrytyczne — upewnij się, że shell je obsługuje",
                code="diacritics_warning",
            ))

        return str(path)

    @staticmethod
    def _has_diacritics(text: str) -> bool:
        """Sprawdź czy tekst zawiera znaki diakrytyczne (np. ąćęłńóśźż)."""
        diacritics = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
        return any(char in text for char in diacritics)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.data_path = self.cleaned_data["folder_path"]
        if commit:
            instance.save()
        return instance


class ImageFrameForm(forms.ModelForm):
    class Meta:
        model = ImageFrame
        fields = ["image_file", "frame_index"]


class CameraPoseForm(forms.ModelForm):
    class Meta:
        model = CameraPose
        fields = ["tx", "ty", "tz", "qw", "qx", "qy", "qz"]


class ExperimentRunForm(forms.ModelForm):
    config_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Wpisz JSON, np. {\"max_num_iterations\": 5000}",
        initial='{"max_num_iterations": 5000}',
    )

    class Meta:
        model = ExperimentRun
        fields = ["name", "dataset", "pipeline_type", "config_json"]

    def clean_config_json(self):
        raw = self.cleaned_data["config_json"].strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Niepoprawny JSON: {exc}") from exc

