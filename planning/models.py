from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from garage.models import Vehicle
from maintenance.models import MONEY, Category


class MaintenancePlan(models.Model):
    class Kind(models.TextChoices):
        MANUFACTURER = "manufacturer", "Recomendação do fabricante"
        USAGE = "usage", "Preventiva pelo uso"
        INSPECTION = "inspection", "Inspeção sugerida"
        DIAGNOSIS = "diagnosis", "Precisa de diagnóstico profissional"

    class Priority(models.TextChoices):
        LOW = "low", "Baixa"
        MEDIUM = "medium", "Média"
        HIGH = "high", "Alta"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SCHEDULED = "scheduled", "Programada"
        DONE = "done", "Realizada"
        DISMISSED = "dismissed", "Descartada"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="plans")
    title = models.CharField("O que fazer", max_length=120)
    category = models.CharField("Categoria", max_length=16, choices=Category.choices, blank=True)
    kind = models.CharField("Tipo", max_length=12, choices=Kind.choices, default=Kind.USAGE)
    priority = models.CharField("Prioridade", max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    reason = models.TextField("Por que fazer", blank=True, max_length=2000)
    interval_km = models.PositiveIntegerField("A cada (km)", null=True, blank=True,
                                              validators=[MinValueValidator(1), MaxValueValidator(500_000)])
    interval_months = models.PositiveSmallIntegerField("A cada (meses)", null=True, blank=True,
                                                       validators=[MinValueValidator(1), MaxValueValidator(240)])
    next_km = models.PositiveIntegerField("Próxima vez (km)", null=True, blank=True, validators=[MaxValueValidator(9_999_999)])
    next_date = models.DateField("Próxima vez (data)", null=True, blank=True)
    status = models.CharField("Situação", max_length=10, choices=Status.choices, default=Status.PENDING)
    scheduled_for = models.DateField("Programada para", null=True, blank=True)
    dismissed_reason = models.CharField("Motivo do descarte", max_length=300, blank=True)
    estimated_cost = models.DecimalField("Custo estimado (R$)", **MONEY)
    source = models.CharField("Fonte", max_length=200, blank=True)
    source_verified = models.BooleanField("Conferi esta informação na fonte", default=False)
    suggestion_key = models.CharField(max_length=40, blank=True, editable=False)
    notes = models.TextField("Observações", blank=True, max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "pk"]
        constraints = [models.UniqueConstraint(fields=["vehicle", "suggestion_key"], condition=~Q(suggestion_key=""),
                                               name="one_plan_per_suggestion")]

    def __str__(self):
        return self.title

    @property
    def is_recurring(self):
        return bool(self.interval_km or self.interval_months)

    @property
    def needs_validation(self):
        return self.kind == self.Kind.MANUFACTURER and not self.source_verified

    @property
    def is_open(self):
        return self.status in (self.Status.PENDING, self.Status.SCHEDULED)

    def clean(self):
        super().clean()
        if self.source_verified and not self.source.strip():
            raise ValidationError({"source": "Informe a fonte que você conferiu (ex.: manual, página)."})
        if self.status == self.Status.SCHEDULED and not self.scheduled_for:
            raise ValidationError({"scheduled_for": "Informe a data programada."})
        if self.status == self.Status.DISMISSED and not self.dismissed_reason.strip():
            raise ValidationError({"dismissed_reason": "Explique por que este item foi descartado."})


class AlertPreferences(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_preferences")
    km_ahead = models.PositiveIntegerField("Avisar quando faltar (km)", default=1000,
                                           validators=[MaxValueValidator(20_000)])
    days_ahead = models.PositiveSmallIntegerField("Avisar quando faltar (dias)", default=30,
                                                  validators=[MaxValueValidator(365)])
    reading_reminder_days = models.PositiveSmallIntegerField("Lembrar de atualizar o km após (dias)", default=30,
                                                             validators=[MinValueValidator(7), MaxValueValidator(365)])
    show_high = models.BooleanField("Mostrar alertas de prioridade alta", default=True)
    show_medium = models.BooleanField("Mostrar alertas de prioridade média", default=True)
    show_low = models.BooleanField("Mostrar alertas de prioridade baixa", default=True)

    @classmethod
    def for_user(cls, user):
        return cls.objects.get_or_create(owner=user)[0]

    def allows(self, level):
        return getattr(self, f"show_{level}")
