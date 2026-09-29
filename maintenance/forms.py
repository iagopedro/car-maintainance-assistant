import re
from decimal import Decimal

from django import forms
from django.utils import timezone

from garage.forms import StyledFormMixin

from .attachments import AttachmentField
from .models import Category, Problem, ProblemUpdate, ServicePart, ServiceRecord

SERVICE_SUGGESTIONS = [
    "Troca de óleo e filtro de óleo", "Troca de filtro de ar", "Troca de filtro de combustível",
    "Troca de filtro de cabine", "Alinhamento e balanceamento", "Rodízio de pneus", "Troca de pneus",
    "Troca de pastilhas de freio", "Troca de fluido de freio", "Troca de bateria", "Troca de palhetas",
    "Revisão geral", "Higienização do ar-condicionado", "Troca de lâmpada", "Instalação de som",
]
LOCATION_SUGGESTIONS = [
    "Motor (cofre)", "Painel", "Interior / cabine", "Dianteira esquerda", "Dianteira direita",
    "Traseira esquerda", "Traseira direita", "Porta esquerda", "Porta direita", "Porta-malas",
    "Parte de baixo do carro", "Não sei",
]


def normalize_money(value):
    text = re.sub(r"\s|R\$", "", value)
    if "," in text:
        return text.replace(".", "").replace(",", ".")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        return text.replace(".", "")
    return text


class MoneyField(forms.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=10, decimal_places=2, min_value=0, required=False,
                         widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00", "autocomplete": "off"}),
                         **kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            value = normalize_money(value)
        return super().to_python(value)

    def prepare_value(self, value):
        if isinstance(value, Decimal):
            return f"{value:.2f}".replace(".", ",")
        return value


def date_widget():
    return forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "max": timezone.localdate().isoformat()})


UNKNOWN_DATE_HELP = "Deixe em branco se não souber."


class ServiceForm(StyledFormMixin, forms.ModelForm):
    parts_cost = MoneyField(label="Peças (R$)")
    labor_cost = MoneyField(label="Mão de obra (R$)")
    total_cost = MoneyField(label="Valor total (R$)", help_text="Opcional. Se preencher peças e mão de obra, o total é calculado.")
    resolves = forms.ModelChoiceField(label="Este serviço resolveu algum problema?", required=False,
                                      queryset=Problem.objects.none(), empty_label="Não / não se aplica")
    attachments = AttachmentField()

    class Meta:
        model = ServiceRecord
        fields = ["category", "title", "date", "kilometers", "total_cost", "kind", "workshop", "parts_cost",
                  "labor_cost", "warranty_until", "warranty_notes", "description", "notes"]
        widgets = {
            "date": date_widget(), "warranty_until": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "kind": forms.RadioSelect, "title": forms.TextInput(attrs={"list": "service-suggestions", "placeholder": "Ex.: Troca de óleo e filtro"}),
            "workshop": forms.TextInput(attrs={"list": "workshop-suggestions", "autocomplete": "off"}),
        }
        help_texts = {"date": UNKNOWN_DATE_HELP, "title": "Opcional. Sem título, a categoria é usada."}

    DETAIL_FIELDS = ["kind", "workshop", "parts_cost", "labor_cost", "warranty_until", "warranty_notes",
                     "description", "notes", "resolves"]

    def __init__(self, *args, vehicle, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Escolha a categoria"), *Category.choices]
        self.fields["title"].label = "O que foi feito?"
        latest = vehicle.latest_reading
        self.fields["kilometers"].help_text = (
            f"Última leitura: {latest.kilometers:,} km em {latest.date:%d/%m/%Y}.".replace(",", ".") if latest
            else "Opcional."
        ) + " Com data e km, a quilometragem do carro também é atualizada."
        problems = vehicle.problems.filter(status__in=Problem.ACTIVE_STATUSES)
        if problems.exists():
            self.fields["resolves"].queryset = problems
        else:
            del self.fields["resolves"]

    def clean(self):
        cleaned = super().clean()
        problem = cleaned.get("resolves")
        service_date = cleaned.get("date")
        if problem and service_date and problem.reported_on and service_date < problem.reported_on:
            self.add_error("resolves", "O serviço é anterior ao relato deste problema.")
        return cleaned

    @property
    def details_have_content(self):
        return any(self.errors.get(name) for name in self.DETAIL_FIELDS) or bool(
            self.instance.pk and any(getattr(self.instance, name, None) not in (None, "", ServiceRecord.Kind.UNSPECIFIED)
                                     for name in self.DETAIL_FIELDS if name != "resolves"))


class PartForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ServicePart
        fields = ["name", "brand_model"]


PartFormSet = forms.inlineformset_factory(ServiceRecord, ServicePart, form=PartForm, extra=1, can_delete=True,
                                          max_num=30, validate_max=True)


class ServiceFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Buscar", required=False, max_length=100,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Serviço, oficina ou peça"}))
    category = forms.ChoiceField(label="Categoria", required=False, choices=[("", "Todas"), *Category.choices])
    start = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start") and cleaned.get("end") and cleaned["start"] > cleaned["end"]:
            raise forms.ValidationError("A data inicial deve ser anterior ou igual à final.")
        return cleaned


class ProblemForm(StyledFormMixin, forms.ModelForm):
    attachments = AttachmentField(help_text="JPG, PNG, WEBP, HEIC ou PDF, até 10 MB cada.")

    class Meta:
        model = Problem
        fields = ["symptom", "description", "reported_on", "kilometers", "location", "severity", "title", "category",
                  "status", "diagnosis", "ruled_out", "solution", "resolved_on", "resolved_by_service"]
        widgets = {
            "symptom": forms.RadioSelect, "severity": forms.RadioSelect, "reported_on": date_widget(),
            "resolved_on": date_widget(), "location": forms.TextInput(attrs={"list": "location-suggestions", "autocomplete": "off"}),
            "description": forms.Textarea(attrs={"placeholder": "Ex.: barulho de líquido na traseira ao frear"}),
        }
        help_texts = {
            "reported_on": UNKNOWN_DATE_HELP, "title": "Opcional. Sem título, usamos o início da descrição.",
            "ruled_out": "Evita repetir investigações já feitas.",
            "severity": "Sua percepção, não um diagnóstico.",
        }

    DETAIL_FIELDS = ["title", "category", "status", "diagnosis", "ruled_out", "solution", "resolved_on", "resolved_by_service"]

    def __init__(self, *args, vehicle, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["symptom"].choices = Problem.Symptom.choices
        self.fields["severity"].choices = Problem.Severity.choices
        self.fields["category"].choices = [("", "Não sei"), *Category.choices]
        self.fields["resolved_by_service"].queryset = vehicle.services.all()
        self.fields["resolved_by_service"].empty_label = "Nenhum"

    @property
    def details_have_content(self):
        return any(self.errors.get(name) for name in self.DETAIL_FIELDS) or bool(
            self.instance.pk or self.initial.get("status") not in (None, Problem.Status.OPEN))


class ProblemUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProblemUpdate
        fields = ["date", "status", "note"]
        widgets = {"date": date_widget(), "note": forms.Textarea(attrs={"rows": 3, "placeholder": "Ex.: levei à oficina, voltou a acontecer, mecânico sugeriu..."})}

    def __init__(self, *args, problem, **kwargs):
        super().__init__(*args, **kwargs)
        self.problem = problem
        self.fields["status"].choices = [("", f"Manter: {problem.get_status_display()}"),
                                         *[c for c in Problem.Status.choices if c[0] != problem.status]]
        self.fields["note"].widget.attrs["rows"] = 3

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("note", "").strip() and not cleaned.get("status"):
            raise forms.ValidationError("Escreva o que aconteceu ou altere a situação.")
        update_date = cleaned.get("date")
        if update_date and self.problem.reported_on and update_date < self.problem.reported_on:
            self.add_error("date", "A atualização não pode ser anterior ao relato.")
        return cleaned


class ProblemFilterForm(StyledFormMixin, forms.Form):
    VIEWS = [("active", "Em aberto"), ("closed", "Resolvidos"), ("all", "Todos")]
    view = forms.ChoiceField(required=False, choices=VIEWS)
    q = forms.CharField(label="Buscar", required=False, max_length=100,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Descrição, local ou diagnóstico"}))


class AttachmentUploadForm(forms.Form):
    attachments = AttachmentField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachments"].widget.attrs.update({"data-autosubmit": "", "aria-label": "Adicionar fotos ou PDF"})
