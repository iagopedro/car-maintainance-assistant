from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from garage.context import get_active_vehicle

from .alerts import planning_overview
from .catalog import SUGGESTIONS
from .forms import DismissForm, LinkServiceForm, PlanForm, PreferencesForm, ScheduleForm, SuggestionForm
from .models import AlertPreferences, MaintenancePlan
from .rules import evaluate
from .services import add_suggestions, dismiss, link_service, reactivate, schedule

GROUPS = [
    ("overdue", "Passaram da referência"),
    ("soon", "Chegando"),
    ("needs_km", "Atualize a quilometragem"),
    ("unknown", "Sem referência"),
    ("scheduled", "Programados"),
    ("ok", "Em dia"),
]


def owned_plan(request, pk):
    return get_object_or_404(MaintenancePlan.objects.select_related("vehicle"), pk=pk, vehicle__owner=request.user)


def with_due(plan, prefs):
    plan.due = evaluate(plan, list(plan.services.all()), plan.vehicle.latest_reading, timezone.localdate(),
                        prefs.km_ahead, prefs.days_ahead)
    return plan


@login_required
def plan_list(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    prefs, plans, _ = planning_overview(request)
    closed_view = request.GET.get("view") == "closed"
    open_plans = [plan for plan in plans if plan.is_open]
    closed_plans = [plan for plan in plans if not plan.is_open]
    groups = [(key, label, [plan for plan in open_plans if plan.due.state == key]) for key, label in GROUPS]
    attention = [plan for plan in open_plans if plan.due.state in ("overdue", "soon")]
    estimates = [plan.estimated_cost for plan in attention if plan.estimated_cost is not None]
    return render(request, "planning/plan_list.html", {
        "vehicle": vehicle, "groups": [group for group in groups if group[2]], "closed_plans": closed_plans,
        "closed_view": closed_view, "open_count": len(open_plans), "section": "plan",
        "estimate_total": sum(estimates, Decimal("0")) if estimates else None, "estimate_count": len(estimates),
        "attention_count": len(attention),
        "missing_suggestions": len(SUGGESTIONS) - vehicle.plans.exclude(suggestion_key="").count(),
    })


def plan_form_view(request, vehicle, plan):
    creating = plan.pk is None
    form = PlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        messages.success(request, "Item adicionado ao plano." if creating else "Item atualizado.")
        return redirect("plan_detail", pk=plan.pk)
    return render(request, "planning/plan_form.html", {
        "form": form, "plan": plan, "vehicle": vehicle, "creating": creating,
        "suggestions": SUGGESTIONS, "section": "plan",
    })


@login_required
def plan_create(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    return plan_form_view(request, vehicle, MaintenancePlan(vehicle=vehicle))


@login_required
def plan_edit(request, pk):
    plan = owned_plan(request, pk)
    return plan_form_view(request, plan.vehicle, plan)


@login_required
def plan_detail(request, pk):
    plan = with_due(owned_plan(request, pk), AlertPreferences.for_user(request.user))
    return render(request, "planning/plan_detail.html", {
        "plan": plan, "vehicle": plan.vehicle, "services": plan.services.all(),
        "schedule_form": ScheduleForm(initial={"scheduled_for": plan.scheduled_for}),
        "dismiss_form": DismissForm(), "link_form": LinkServiceForm(plan=plan), "section": "plan",
    })


@login_required
@require_POST
def plan_action(request, pk, action):
    plan = owned_plan(request, pk)
    if action == "programar":
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule(plan, form.cleaned_data["scheduled_for"])
            messages.success(request, f"Programado para {plan.scheduled_for:%d/%m/%Y}.")
    elif action == "descartar":
        form = DismissForm(request.POST)
        if form.is_valid():
            dismiss(plan, form.cleaned_data["dismissed_reason"])
            messages.success(request, "Item descartado. Você pode reativá-lo quando quiser.")
    elif action == "reativar":
        form = None
        reactivate(plan)
        messages.success(request, "Item reativado.")
    elif action == "vincular":
        form = LinkServiceForm(request.POST, plan=plan)
        if form.is_valid():
            link_service(plan, form.cleaned_data["service"])
            messages.success(request, "Serviço vinculado. A próxima referência foi recalculada.")
    else:
        return redirect("plan_detail", pk=plan.pk)
    if form is not None and not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect("plan_detail", pk=plan.pk)


@login_required
def plan_delete(request, pk):
    plan = owned_plan(request, pk)
    if request.method == "POST":
        plan.delete()
        messages.success(request, "Item removido do plano. Os serviços registrados foram mantidos.")
        return redirect("plan_list")
    return render(request, "planning/plan_confirm_delete.html", {"plan": plan, "section": "plan"})


@login_required
def suggestions(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    form = SuggestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        created = add_suggestions(vehicle, form.cleaned_data["keys"])
        messages.success(request, f"{len(created)} ite{'m adicionado' if len(created) == 1 else 'ns adicionados'}. "
                                  "Informe os intervalos do manual para ativar os avisos por km e data.")
        return redirect("plan_list")
    added = set(vehicle.plans.exclude(suggestion_key="").values_list("suggestion_key", flat=True))
    return render(request, "planning/suggestions.html", {
        "vehicle": vehicle, "form": form, "suggestions": SUGGESTIONS, "added": added, "section": "plan",
    })


@login_required
def alert_list(request):
    vehicle = get_active_vehicle(request)
    _, _, alerts = planning_overview(request) if vehicle else (None, None, [])
    return render(request, "planning/alert_list.html", {"vehicle": vehicle, "alerts": alerts, "section": "alerts"})


@login_required
def alert_settings(request):
    prefs = AlertPreferences.for_user(request.user)
    form = PreferencesForm(request.POST or None, instance=prefs)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Preferências de alerta salvas.")
        return redirect(reverse("alert_list"))
    return render(request, "planning/alert_settings.html", {"form": form, "section": "alerts"})
