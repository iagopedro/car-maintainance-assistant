from django import forms

from garage.forms import StyledFormMixin
from maintenance.forms import LOCATION_SUGGESTIONS
from maintenance.models import Problem

from .models import UsageProfile


class SymptomForm(StyledFormMixin, forms.Form):
    symptom = forms.ChoiceField(label="O que você percebeu?", choices=Problem.Symptom.choices, widget=forms.RadioSelect)
    description = forms.CharField(label="Descreva com suas palavras", max_length=2000,
                                  widget=forms.Textarea(attrs={"rows": 3, "placeholder":
                                                               "Ex.: chiado agudo ao frear, mais forte de manhã"}),
                                  help_text="Diga quando acontece: ao frear, em curvas, em buracos, parado, frio ou quente.")
    location = forms.CharField(label="Onde no carro (opcional)", max_length=120, required=False,
                               widget=forms.TextInput(attrs={"list": "location-suggestions", "autocomplete": "off"}))
    severity = forms.ChoiceField(label="Gravidade percebida", choices=Problem.Severity.choices, widget=forms.RadioSelect,
                                 initial=Problem.Severity.UNKNOWN)

    location_suggestions = LOCATION_SUGGESTIONS


class UsageProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = UsageProfile
        fields = UsageProfile.FLAGS
