from django import forms

from garage.forms import StyledFormMixin
from maintenance.forms import MoneyField
from maintenance.models import Category

from .catalog import SUGGESTIONS
from .models import AlertPreferences, MaintenancePlan


class PlanForm(StyledFormMixin, forms.ModelForm):
    estimated_cost = MoneyField(label="Custo estimado (R$)")

    class Meta:
        model = MaintenancePlan
        fields = ["title", "kind", "priority", "interval_km", "interval_months", "next_km", "next_date", "category",
                  "reason", "estimated_cost", "source", "source_verified", "notes"]
        widgets = {
            "kind": forms.RadioSelect, "priority": forms.RadioSelect,
            "title": forms.TextInput(attrs={"list": "plan-suggestions", "placeholder": "Ex.: Troca de óleo e filtro"}),
            "next_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "source": forms.TextInput(attrs={"placeholder": "Ex.: Manual do proprietário, página 120"}),
        }
        help_texts = {
            "interval_km": "Para itens que se repetem. Use o valor do manual.",
            "interval_months": "O que ocorrer primeiro, km ou tempo, gera o aviso.",
            "next_km": "Opcional. Substitui o cálculo pelo intervalo.",
            "source_verified": "Marque só depois de conferir no manual ou com o fabricante.",
        }

    DETAIL_FIELDS = ["category", "reason", "estimated_cost", "source", "source_verified", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Não definida"), *Category.choices]

    @property
    def details_have_content(self):
        return any(self.errors.get(name) for name in self.DETAIL_FIELDS) or bool(
            self.instance.pk or self.initial.get("source"))


class ScheduleForm(forms.Form):
    scheduled_for = forms.DateField(label="Data programada", widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))


class DismissForm(forms.Form):
    dismissed_reason = forms.CharField(label="Por que descartar?", max_length=300,
                                       widget=forms.TextInput(attrs={"class": "form-control",
                                                                     "placeholder": "Ex.: não se aplica ao meu motor"}))


class LinkServiceForm(forms.Form):
    service = forms.ModelChoiceField(label="Serviço já registrado", queryset=None, empty_label="Escolha o serviço",
                                     widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, plan, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = plan.vehicle.services.filter(plan__isnull=True)


class SuggestionForm(forms.Form):
    keys = forms.MultipleChoiceField(choices=[(s.key, s.title) for s in SUGGESTIONS], widget=forms.CheckboxSelectMultiple,
                                     error_messages={"required": "Escolha pelo menos um item."})


class PreferencesForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AlertPreferences
        fields = ["km_ahead", "days_ahead", "reading_reminder_days", "show_high", "show_medium", "show_low"]
        help_texts = {
            "km_ahead": "Apenas a antecedência do aviso, não um intervalo de manutenção.",
            "reading_reminder_days": "Com o km atualizado, os alertas por km ficam precisos.",
        }
