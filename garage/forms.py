from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.utils import timezone

from .models import OdometerReading, Vehicle


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            widget.attrs["class"] = (
                "form-check-input" if isinstance(widget, forms.CheckboxInput)
                else "chip-input" if isinstance(widget, forms.RadioSelect)
                else "form-select" if isinstance(widget, forms.Select)
                else "form-control"
            )
            auto_id = self[name].auto_id
            widget.attrs["aria-describedby"] = f"{auto_id}_help {auto_id}_errors"
            if isinstance(widget, forms.Textarea):
                widget.attrs["rows"] = 4
            if isinstance(widget, forms.NumberInput):
                widget.attrs["inputmode"] = "numeric"


class SetupForm(StyledFormMixin, UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "username"


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass


class OwnerPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


class VehicleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["brand", "model", "model_year", "version", "manufacture_year", "engine",
                  "engine_verified", "fuel", "acquisition_date", "plate", "notes"]
        widgets = {"acquisition_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        labels = {
            "version": "Versão", "manufacture_year": "Ano de fabricação",
            "engine": "Motorização informada", "engine_verified": "Conferida na documentação do veículo",
            "fuel": "Combustível", "acquisition_date": "Data de aquisição", "notes": "Observações e perfil de uso",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["acquisition_date"].widget.attrs["max"] = timezone.localdate().isoformat()
        self.fields["model_year"].widget.attrs["max"] = timezone.localdate().year + 1


class VehicleCreateForm(VehicleForm):
    initial_kilometers = forms.IntegerField(label="Quilometragem atual (km)", required=False, min_value=0, max_value=9999999)
    reading_date = forms.DateField(label="Data da leitura", required=False, initial=timezone.localdate,
                                   widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("initial_kilometers") is not None and not cleaned.get("reading_date"):
            self.add_error("reading_date", "Informe a data dessa quilometragem.")
        if cleaned.get("reading_date") and cleaned["reading_date"] > timezone.localdate():
            self.add_error("reading_date", "A leitura não pode estar no futuro.")
        return cleaned


class ReadingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = OdometerReading
        fields = ["date", "kilometers", "source", "notes"]
        widgets = {"date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        labels = {"notes": "Observação (opcional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].widget.attrs["max"] = timezone.localdate().isoformat()
        self.fields["source"].choices = [
            choice for choice in OdometerReading.Source.choices if choice[0] != OdometerReading.Source.SERVICE
        ]


class ReadingFilterForm(StyledFormMixin, forms.Form):
    start = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    source = forms.ChoiceField(label="Origem", required=False, choices=[("", "Todas as origens"), *OdometerReading.Source.choices])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start") and cleaned.get("end") and cleaned["start"] > cleaned["end"]:
            raise forms.ValidationError("A data inicial deve ser anterior ou igual à final.")
        return cleaned