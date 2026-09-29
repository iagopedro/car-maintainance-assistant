from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Installation(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class Vehicle(models.Model):
    class Fuel(models.TextChoices):
        UNKNOWN = "unknown", "A confirmar"
        FLEX = "flex", "Flex"
        GASOLINE = "gasoline", "Gasolina"
        ETHANOL = "ethanol", "Etanol"
        DIESEL = "diesel", "Diesel"
        ELECTRIC = "electric", "Elétrico"
        HYBRID = "hybrid", "Híbrido"
        OTHER = "other", "Outro"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    brand = models.CharField("Marca", max_length=80)
    model = models.CharField("Modelo", max_length=100)
    version = models.CharField("Versao", max_length=100, blank=True)
    manufacture_year = models.PositiveSmallIntegerField("Ano de fabricacao", null=True, blank=True, validators=[MinValueValidator(1886), MaxValueValidator(2100)])
    model_year = models.PositiveSmallIntegerField("Ano-modelo", validators=[MinValueValidator(1886), MaxValueValidator(2100)])
    engine = models.CharField("Motorizacao informada", max_length=120, blank=True)
    engine_verified = models.BooleanField("Motorizacao conferida na documentacao", default=False)
    fuel = models.CharField("Combustivel", max_length=12, choices=Fuel.choices, default=Fuel.UNKNOWN)
    acquisition_date = models.DateField("Data de aquisicao", null=True, blank=True)
    plate = models.CharField("Placa (opcional)", max_length=12, blank=True)
    notes = models.TextField("Observacoes e perfil de uso", blank=True, max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["brand", "model", "pk"]

    def __str__(self):
        return f"{self.brand} {self.model} {self.model_year}"

    def clean(self):
        super().clean()
        if self.acquisition_date and self.acquisition_date > timezone.localdate():
            raise ValidationError({"acquisition_date": "A aquisição não pode estar no futuro."})
        if self.manufacture_year and self.manufacture_year > self.model_year:
            raise ValidationError({"manufacture_year": "A fabricação não pode ser posterior ao ano-modelo."})
        if self.model_year and self.model_year > timezone.localdate().year + 1:
            raise ValidationError({"model_year": "Confira o ano-modelo informado."})
        if self.engine_verified and not self.engine.strip():
            raise ValidationError({"engine": "Informe a motorização conferida."})

    @property
    def latest_reading(self):
        return self.readings.order_by("-date", "-pk").first()


def odometer_conflict(vehicle_id, date, kilometers, exclude_pk=None):
    readings = OdometerReading.objects.filter(vehicle_id=vehicle_id).exclude(pk=exclude_pk)
    previous = readings.filter(date__lt=date).first()
    following = readings.filter(date__gt=date).order_by("date", "pk").first()
    if previous and kilometers < previous.kilometers:
        return (f"O valor é menor que a leitura de {previous.kilometers:,} km em {previous.date:%d/%m/%Y}. "
                "Revise a data ou a quilometragem.").replace(",", ".")
    if following and kilometers > following.kilometers:
        return (f"O valor é maior que a leitura de {following.kilometers:,} km em {following.date:%d/%m/%Y}. "
                "Revise a data ou a quilometragem.").replace(",", ".")
    return None


class OdometerReading(models.Model):
    class Source(models.TextChoices):
        PANEL = "panel", "Painel do veículo"
        DOCUMENT = "document", "Documento ou comprovante"
        HISTORY = "history", "Histórico informado"
        SERVICE = "service", "Registro de serviço"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="readings")
    date = models.DateField("Data da leitura", default=timezone.localdate)
    kilometers = models.PositiveIntegerField("Quilometragem (km)", validators=[MaxValueValidator(9999999)])
    source = models.CharField("Origem", max_length=12, choices=Source.choices, default=Source.PANEL)
    notes = models.CharField("Observacao (opcional)", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [models.UniqueConstraint(fields=["vehicle", "date"], name="one_reading_per_vehicle_day")]

    def clean(self):
        super().clean()
        if self.date and self.date > timezone.localdate():
            raise ValidationError({"date": "A leitura não pode estar no futuro."})
        if not self.vehicle_id or self.date is None or self.kilometers is None:
            return
        conflict = odometer_conflict(self.vehicle_id, self.date, self.kilometers, exclude_pk=self.pk)
        if conflict:
            raise ValidationError({"kilometers": conflict})