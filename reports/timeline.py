from dataclasses import dataclass
from datetime import date

from django.urls import reverse
from django.utils.formats import date_format

from garage.models import OdometerReading
from maintenance.models import Category, Problem, ServiceRecord
from maintenance.templatetags.maintenance_tags import CATEGORY_ICONS, SYMPTOM_ICONS, brl
from planning.rules import fmt_km

TYPES = [("", "Tudo"), ("services", "Serviços"), ("problems", "Problemas"), ("readings", "Quilometragem"),
         ("upcoming", "Próximas manutenções")]
STATUSES = [("", "Qualquer situação"), ("preventive", "Serviço preventivo"), ("corrective", "Serviço corretivo"),
            ("inspection", "Inspeção"), ("open", "Problema em aberto"), ("resolved", "Problema resolvido ou encerrado")]
SERVICE_STATUSES = {"preventive", "corrective", "inspection"}
PROBLEM_STATUSES = {"open", "resolved"}


@dataclass(frozen=True)
class Entry:
    date: date | None
    kind: str
    title: str
    detail: str
    url: str
    icon: str
    tag: str = ""
    tone: str = ""
    amount: str = ""
    order: int = 0

    @property
    def group(self):
        return date_format(self.date, "F \\d\\e Y").capitalize() if self.date else "Data desconhecida"


def service_entries(vehicle, filters):
    services = vehicle.services.prefetch_related("parts")
    if filters.get("category"):
        services = services.filter(category=filters["category"])
    if filters.get("status") in SERVICE_STATUSES:
        services = services.filter(kind=filters["status"])
    for service in services:
        parts = ", ".join(part.name for part in service.parts.all())
        detail = " · ".join(filter(None, [
            f"{fmt_km(service.kilometers)} km" if service.kilometers is not None else "",
            service.workshop, f"Peças: {parts}" if parts else ""]))
        yield Entry(service.date, "service", service.display_title, detail or service.get_category_display(),
                    reverse("service_detail", args=[service.pk]), CATEGORY_ICONS.get(service.category, "wrench"),
                    service.get_kind_display() if service.kind != ServiceRecord.Kind.UNSPECIFIED else "Serviço",
                    service.kind, brl(service.total_cost) if service.total_cost is not None else "", service.pk)


def problem_entries(vehicle, filters):
    problems = vehicle.problems.prefetch_related("updates")
    if filters.get("category"):
        problems = problems.filter(category=filters["category"])
    status = filters.get("status")
    if status == "open":
        problems = problems.filter(status__in=Problem.ACTIVE_STATUSES)
    elif status == "resolved":
        problems = problems.exclude(status__in=Problem.ACTIVE_STATUSES)
    for problem in problems:
        url = reverse("problem_detail", args=[problem.pk])
        detail = " · ".join(filter(None, [problem.get_symptom_display(), problem.location,
                                          f"{fmt_km(problem.kilometers)} km" if problem.kilometers is not None else ""]))
        yield Entry(problem.reported_on, "problem", f"Relato: {problem.display_title}", detail, url,
                    SYMPTOM_ICONS.get(problem.symptom, "message-circle"), problem.get_status_display(),
                    f"problem-{problem.status}", order=problem.pk)
        for update in problem.updates.all():
            label = update.get_status_display() if update.status else "Acompanhamento"
            yield Entry(update.date, "update", f"{label}: {problem.display_title}", update.note, url,
                        "message-square-text", label, f"problem-{update.status or 'note'}", order=update.pk)


def reading_entries(vehicle):
    for reading in vehicle.readings.exclude(source=OdometerReading.Source.SERVICE):
        yield Entry(reading.date, "reading", f"{fmt_km(reading.kilometers)} km", reading.get_source_display(),
                    reverse("reading_list", args=[vehicle.pk]), "gauge", "Quilometragem", "reading", order=reading.pk)


def upcoming_entries(plans, filters):
    for plan in plans:
        if not plan.is_open or plan.due.state not in ("overdue", "soon", "scheduled", "ok"):
            continue
        if filters.get("category") and plan.category != filters["category"]:
            continue
        yield Entry(plan.due.next_date or plan.scheduled_for, "upcoming", plan.title, plan.due.summary,
                    reverse("plan_detail", args=[plan.pk]), "calendar-clock", plan.due.label, f"due-{plan.due.state}",
                    brl(plan.estimated_cost) if plan.estimated_cost is not None else "", plan.pk)


def in_period(entry, start, end):
    if not start and not end:
        return True
    if entry.date is None:
        return False
    return (not start or entry.date >= start) and (not end or entry.date <= end)


def build_timeline(vehicle, plans, filters):
    kind, status = filters.get("type") or "", filters.get("status") or ""
    history = []

    def wants(name):
        return kind in ("", name)

    if wants("services") and status not in PROBLEM_STATUSES:
        history.extend(service_entries(vehicle, filters))
    if wants("problems") and status not in SERVICE_STATUSES:
        history.extend(problem_entries(vehicle, filters))
    if wants("readings") and not status and not filters.get("category"):
        history.extend(reading_entries(vehicle))
    start, end = filters.get("start"), filters.get("end")
    history = [entry for entry in history if in_period(entry, start, end)]
    history.sort(key=lambda entry: (entry.date is not None, entry.date or date.min, entry.order), reverse=True)
    upcoming = []
    if wants("upcoming") and not status:
        upcoming = sorted(upcoming_entries(plans, filters), key=lambda entry: (entry.date is None, entry.date or date.max))
    return upcoming, history


CATEGORY_CHOICES = [("", "Todas as categorias"), *Category.choices]
