from django import forms

from garage.forms import StyledFormMixin

from .timeline import CATEGORY_CHOICES, STATUSES, TYPES


class TimelineFilterForm(StyledFormMixin, forms.Form):
    type = forms.ChoiceField(label="Mostrar", required=False, choices=TYPES)
    category = forms.ChoiceField(label="Categoria", required=False, choices=CATEGORY_CHOICES)
    status = forms.ChoiceField(label="Situação", required=False, choices=STATUSES)
    start = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start") and cleaned.get("end") and cleaned["start"] > cleaned["end"]:
            raise forms.ValidationError("A data inicial deve ser anterior ou igual à final.")
        return cleaned

    @property
    def has_extra_filters(self):
        return any(self.data.get(name) for name in ("category", "status", "start", "end"))


class RestoreForm(forms.Form):
    backup = forms.FileField(label="Arquivo de backup (.zip)",
                             widget=forms.ClearableFileInput(attrs={"accept": ".zip,application/zip", "class": "form-control"}))
    confirm = forms.BooleanField(label="Entendo que os dados do arquivo serão importados para esta conta.",
                                 widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
