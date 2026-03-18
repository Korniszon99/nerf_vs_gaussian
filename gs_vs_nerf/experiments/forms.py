import json

from django import forms

from .models import CameraPose, Dataset, ExperimentRun, ImageFrame


class DatasetForm(forms.ModelForm):
    class Meta:
        model = Dataset
        fields = ["name", "description", "data_path"]


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

