from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

from garage.context import get_active_vehicle
from maintenance.models import Problem

from .models import AlertPreferences
from .rules import evaluate, fmt_km

LEVELS = {"high": (0, "Prioridade alta"), "medium": (1, "Prioridade média"), "low": (2, "Prioridade baixa")}
STALE_PROBLEM_DAYS = 30
RECURRENCE_WINDOW_DAYS = 365


@dataclass(frozen=True)
class Alert:
    level: str
    title: str
    message: str
    url: str
    action: str
    icon: str
    urgent: bool = False

    @property
    def level_label(self):
        return LEVELS[self.level][1]


def evaluate_plans(vehicle, prefs, today):
    reading = vehicle.latest_reading
    plans = list(vehicle.plans.prefetch_related("services"))
    for plan in plans:
        plan.due = evaluate(plan, list(plan.services.all()), reading, today, prefs.km_ahead, prefs.days_ahead)
    return plans


def plan_alerts(plans, today):
    alerts, unknown = [], []
    for plan in plans:
        due, url = plan.due, reverse("plan_detail", args=[plan.pk])
        caution = " O intervalo ainda não foi conferido no manual." if plan.needs_validation else ""
        if due.state == "overdue":
            alerts.append(Alert(plan.priority, f"{plan.title}: passou da referência",
                                f"Referência: {due.target} ({due.remaining}). Vale agendar.{caution}",
                                url, "Ver item", "calendar-clock", urgent=True))
        elif due.state == "soon":
            alerts.append(Alert(plan.priority, f"{plan.title}: está chegando",
                                f"Referência: {due.target} ({due.remaining}).{caution}", url, "Ver item", "calendar-clock"))
        elif due.state == "scheduled" and plan.scheduled_for < today:
            alerts.append(Alert("low", f"{plan.title}: programado para {plan.scheduled_for:%d/%m/%Y}",
                                "Já foi feito? Registre a realização ou reprograme.", url, "Atualizar", "calendar-check"))
        elif due.state == "unknown":
            unknown.append(plan)
        if plan.kind == plan.Kind.DIAGNOSIS and plan.is_open and due.state not in ("overdue", "scheduled"):
            alerts.append(Alert(plan.priority, f"{plan.title}: avaliação profissional",
                                plan.reason or "Item marcado para diagnóstico por um mecânico.", url, "Ver item", "stethoscope"))
    if unknown:
        examples = ", ".join(plan.title for plan in unknown[:3])
        more = f" e mais {len(unknown) - 3}" if len(unknown) > 3 else ""
        alerts.append(Alert("low", f"{len(unknown)} ite{'m' if len(unknown) == 1 else 'ns'} do plano sem referência",
                            f"{examples}{more}. Registre a última realização ou informe o intervalo do manual; "
                            "se não souber, peça avaliação na próxima revisão.",
                            f"{reverse('plan_list')}#grupo-unknown", "Completar", "circle-help"))
    return alerts


def odometer_alerts(vehicle, plans, prefs, today):
    reading = vehicle.latest_reading
    uses_km = any(plan.interval_km or plan.next_km is not None for plan in plans if plan.is_open)
    url = reverse("reading_create", args=[vehicle.pk])
    if reading is None:
        if uses_km:
            return [Alert("medium", "Informe a quilometragem atual",
                          "Sem ela não é possível calcular os itens do plano por km.", url, "Registrar km", "gauge")]
        return []
    age = (today - reading.date).days
    if age >= prefs.reading_reminder_days:
        return [Alert("low", f"Última leitura de km há {age} dias",
                      f"Atualize a quilometragem ({fmt_km(reading.kilometers)} km em {reading.date:%d/%m/%Y}) "
                      "para os alertas por km ficarem precisos.", url, "Registrar km", "gauge")]
    return []


def problem_alerts(vehicle, today):
    alerts = []
    problems = list(vehicle.problems.prefetch_related("updates"))
    for problem in problems:
        if not problem.is_active:
            continue
        url = reverse("problem_detail", args=[problem.pk])
        if problem.severity == Problem.Severity.HIGH:
            alerts.append(Alert("high", f"Problema em aberto: {problem.display_title}",
                                "Você marcou gravidade alta. Recomendamos avaliação profissional; "
                                "este aviso não é um diagnóstico.", url, "Ver problema", "triangle-alert", urgent=True))
        dates = [update.date for update in problem.updates.all()]
        dates.append(problem.reported_on or timezone.localtime(problem.created_at).date())
        idle = (today - max(dates)).days
        if idle >= STALE_PROBLEM_DAYS:
            alerts.append(Alert("low", f"Sem acompanhamento há {idle} dias: {problem.display_title}",
                                "Ainda acontece? Registre uma atualização ou marque como resolvido.",
                                url, "Atualizar", "message-square-warning"))
    groups = defaultdict(list)
    window_start = today - timedelta(days=RECURRENCE_WINDOW_DAYS)
    for problem in problems:
        when = problem.reported_on or timezone.localtime(problem.created_at).date()
        if when >= window_start and problem.location.strip():
            groups[(problem.symptom, problem.location.strip().lower())].append(problem)
    for group in groups.values():
        if len(group) < 2:
            continue
        sample = group[0]
        active = any(problem.is_active for problem in group)
        query = urlencode({"view": "all", "q": sample.location.strip()})
        alerts.append(Alert("medium" if active else "low",
                            f"Sintoma recorrente: {sample.get_symptom_display()} · {sample.location.strip()}",
                            f"{len(group)} relatos nos últimos 12 meses. Leve o histórico completo ao mecânico; "
                            "pode ser a mesma causa ou causas diferentes.",
                            f"{reverse('problem_list')}?{query}", "Ver relatos", "repeat"))
    return alerts


def warranty_alerts(vehicle, prefs, today):
    limit = today + timedelta(days=prefs.days_ahead)
    return [Alert("low", f"Garantia termina em {(service.warranty_until - today).days} dias: {service.display_title}",
                  "Se notar algo relacionado a este serviço, procure a oficina antes do fim da garantia.",
                  reverse("service_detail", args=[service.pk]), "Ver serviço", "shield-check")
            for service in vehicle.services.filter(warranty_until__gte=today, warranty_until__lte=limit)]


def build_alerts(vehicle, prefs, plans, today):
    alerts = [*plan_alerts(plans, today), *problem_alerts(vehicle, today),
              *odometer_alerts(vehicle, plans, prefs, today), *warranty_alerts(vehicle, prefs, today)]
    visible = [alert for alert in alerts if prefs.allows(alert.level)]
    return sorted(visible, key=lambda alert: (not alert.urgent, LEVELS[alert.level][0]))


def planning_overview(request):
    """Per-request cache shared by the dashboard, alert pages and the header badge."""
    if not hasattr(request, "_planning_overview"):
        today = timezone.localdate()
        vehicle = get_active_vehicle(request)
        prefs = AlertPreferences.for_user(request.user)
        plans = evaluate_plans(vehicle, prefs, today) if vehicle else []
        alerts = build_alerts(vehicle, prefs, plans, today) if vehicle else []
        request._planning_overview = (prefs, plans, alerts)
    return request._planning_overview


def alert_count(request):
    if not request.user.is_authenticated:
        return {}
    return {"alert_count": SimpleLazyObject(lambda: len(planning_overview(request)[2]))}
