import logging
import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import Truncator

from garage.models import OdometerReading, Vehicle, odometer_conflict

logger = logging.getLogger(__name__)


class Category(models.TextChoices):
    OIL = "oil", "Óleo e filtro de óleo"
    FILTERS = "filters", "Filtros de ar, combustível e cabine"
    BRAKES = "brakes", "Freios"
    TIRES = "tires", "Pneus, alinhamento e balanceamento"
    SUSPENSION = "suspension", "Suspensão e direção"
    COOLING = "cooling", "Arrefecimento"
    BATTERY = "battery", "Bateria"
    ELECTRICAL = "electrical", "Sistema elétrico e iluminação"
    ENGINE = "engine", "Motor"
    TRANSMISSION = "transmission", "Transmissão e embreagem"
    FUEL = "fuel", "Combustível e injeção"
    BELTS = "belts", "Correias e componentes auxiliares"
    AC = "ac", "Ar-condicionado e ventilação"
    AUDIO = "audio", "Sistema de som"
    BODY = "body", "Carroceria, vedações, pintura e acabamento"
    GENERAL = "general", "Revisão ou inspeção geral"
    OTHER = "other", "Outro"


MONEY = {"max_digits": 10, "decimal_places": 2, "null": True, "blank": True, "validators": [MinValueValidator(0)]}
KILOMETERS = {"null": True, "blank": True, "validators": [MaxValueValidator(9_999_999)]}


def not_in_future(value, field, message):
    if value and value > timezone.localdate():
        raise ValidationError({field: message})


class ServiceRecord(models.Model):
    class Kind(models.TextChoices):
        UNSPECIFIED = "unspecified", "Não classificado"
        PREVENTIVE = "preventive", "Preventiva"
        CORRECTIVE = "corrective", "Corretiva"
        INSPECTION = "inspection", "Inspeção ou avaliação"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="services")
    category = models.CharField("Categoria", max_length=16, choices=Category.choices)
    title = models.CharField("O que foi feito", max_length=120, blank=True)
    date = models.DateField("Data", null=True, blank=True)
    kilometers = models.PositiveIntegerField("Quilometragem (km)", **KILOMETERS)
    kind = models.CharField("Tipo", max_length=12, choices=Kind.choices, default=Kind.UNSPECIFIED)
    workshop = models.CharField("Oficina ou profissional", max_length=120, blank=True)
    description = models.TextField("Descrição", blank=True, max_length=5000)
    parts_cost = models.DecimalField("Peças (R$)", **MONEY)
    labor_cost = models.DecimalField("Mão de obra (R$)", **MONEY)
    total_cost = models.DecimalField("Valor total (R$)", **MONEY)
    warranty_until = models.DateField("Garantia até", null=True, blank=True)
    warranty_notes = models.CharField("Condições da garantia", max_length=200, blank=True)
    notes = models.TextField("Observações", blank=True, max_length=5000)
    odometer_reading = models.OneToOneField(OdometerReading, on_delete=models.SET_NULL, null=True, blank=True,
                                            editable=False, related_name="service")
    plan = models.ForeignKey("planning.MaintenancePlan", on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="services", verbose_name="Item do plano realizado")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [F("date").desc(nulls_last=True), "-pk"]

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        return self.title or self.get_category_display()

    @property
    def warranty_active(self):
        return bool(self.warranty_until and self.warranty_until >= timezone.localdate())

    def clean(self):
        super().clean()
        not_in_future(self.date, "date", "A data do serviço não pode estar no futuro.")
        if self.date and self.warranty_until and self.warranty_until < self.date:
            raise ValidationError({"warranty_until": "A garantia não pode terminar antes do serviço."})
        if self.plan_id and self.plan.vehicle_id != self.vehicle_id:
            raise ValidationError({"plan": "Escolha um item do plano deste veículo."})
        known_parts = [cost for cost in (self.parts_cost, self.labor_cost) if cost is not None]
        if known_parts and self.total_cost is None:
            self.total_cost = sum(known_parts)
        elif known_parts and sum(known_parts) > self.total_cost:
            raise ValidationError({"total_cost": "Peças e mão de obra somam mais que o valor total."})
        if self.vehicle_id and self.date and self.kilometers is not None:
            conflict = odometer_conflict(self.vehicle_id, self.date, self.kilometers, exclude_pk=self.odometer_reading_id)
            if conflict:
                raise ValidationError({"kilometers": conflict})


class ServicePart(models.Model):
    service = models.ForeignKey(ServiceRecord, on_delete=models.CASCADE, related_name="parts")
    name = models.CharField("Peça", max_length=120)
    brand_model = models.CharField("Marca, modelo ou código", max_length=120, blank=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.name


class Problem(models.Model):
    class Symptom(models.TextChoices):
        NOISE = "noise", "Ruído"
        VIBRATION = "vibration", "Vibração"
        WARNING_LIGHT = "warning_light", "Luz no painel"
        STARTING = "starting", "Dificuldade na partida"
        CONSUMPTION = "consumption", "Alteração no consumo"
        MALFUNCTION = "malfunction", "Falha de funcionamento"
        LEAK = "leak", "Vazamento"
        ELECTRICAL = "electrical", "Problema elétrico"
        WEAR = "wear", "Desgaste visual ou estrutural"
        OTHER = "other", "Outro"

    class Severity(models.TextChoices):
        UNKNOWN = "unknown", "Não sei avaliar"
        LOW = "low", "Baixa"
        MEDIUM = "medium", "Média"
        HIGH = "high", "Alta"

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        MONITORING = "monitoring", "Em observação"
        DIAGNOSIS = "diagnosis", "Em diagnóstico"
        RESOLVED = "resolved", "Resolvido"
        CLOSED = "closed", "Encerrado sem conclusão"

    ACTIVE_STATUSES = [Status.OPEN, Status.MONITORING, Status.DIAGNOSIS]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="problems")
    symptom = models.CharField("O que você percebeu?", max_length=16, choices=Symptom.choices)
    title = models.CharField("Título curto", max_length=120, blank=True)
    description = models.TextField("Descreva com suas palavras", max_length=5000)
    reported_on = models.DateField("Quando percebeu", null=True, blank=True)
    kilometers = models.PositiveIntegerField("Quilometragem (km)", **KILOMETERS)
    location = models.CharField("Onde no carro", max_length=120, blank=True)
    category = models.CharField("Sistema relacionado", max_length=16, choices=Category.choices, blank=True)
    severity = models.CharField("Gravidade percebida", max_length=8, choices=Severity.choices, default=Severity.UNKNOWN)
    status = models.CharField("Situação", max_length=12, choices=Status.choices, default=Status.OPEN)
    diagnosis = models.TextField("Diagnóstico realizado", blank=True, max_length=5000)
    ruled_out = models.TextField("Causas já descartadas", blank=True, max_length=2000)
    solution = models.TextField("Solução aplicada", blank=True, max_length=5000)
    resolved_on = models.DateField("Resolvido em", null=True, blank=True)
    resolved_by_service = models.ForeignKey(ServiceRecord, on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name="resolved_problems", verbose_name="Serviço relacionado")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [F("reported_on").desc(nulls_last=True), "-pk"]

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        if self.title:
            return self.title
        lines = self.description.strip().splitlines()
        if lines:
            return Truncator(lines[0]).chars(70)
        label = self.get_symptom_display()
        return f"{label} · {self.location}" if self.location else label

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    def clean(self):
        super().clean()
        not_in_future(self.reported_on, "reported_on", "A data não pode estar no futuro.")
        not_in_future(self.resolved_on, "resolved_on", "A data não pode estar no futuro.")
        if self.reported_on and self.resolved_on and self.resolved_on < self.reported_on:
            raise ValidationError({"resolved_on": "A resolução não pode ser anterior ao relato."})
        if self.resolved_by_service_id and self.resolved_by_service.vehicle_id != self.vehicle_id:
            raise ValidationError({"resolved_by_service": "Escolha um serviço deste veículo."})


class ProblemUpdate(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name="updates")
    date = models.DateField("Data", default=timezone.localdate)
    status = models.CharField("Nova situação", max_length=12, choices=Problem.Status.choices, blank=True)
    note = models.TextField("O que aconteceu?", blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "pk"]


def attachment_path(instance, filename):
    return f"attachments/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Attachment(models.Model):
    IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

    service = models.ForeignKey(ServiceRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    file = models.FileField(upload_to=attachment_path, max_length=200)
    original_name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=50)
    size = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]
        constraints = [models.CheckConstraint(
            condition=Q(service__isnull=False, problem__isnull=True) | Q(service__isnull=True, problem__isnull=False),
            name="attachment_single_owner",
        )]

    @property
    def is_image(self):
        return self.content_type in self.IMAGE_TYPES


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    name, storage = instance.file.name, instance.file.storage

    def remove():
        try:
            storage.delete(name)
        except OSError:
            logger.warning("Could not delete attachment file %s; remove it manually.", name, exc_info=True)

    if name:
        transaction.on_commit(remove)
