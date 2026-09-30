from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from garage.context import get_active_vehicle
from maintenance.models import Problem
from planning.alerts import planning_overview
from planning.catalog import SUGGESTIONS_BY_KEY
from planning.services import add_suggestions

from .engine import USAGE_TIPS, analyze_problem, analyze_symptom, review
from .forms import SymptomForm, UsageProfileForm
from .models import UsageProfile


def profile_for(vehicle):
    return UsageProfile.objects.filter(vehicle=vehicle).first()


@login_required
def home(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    today = timezone.localdate()
    profile = profile_for(vehicle)
    return render(request, "assistant/home.html", {
        "vehicle": vehicle, "profile": profile, "review": review(vehicle, planning_overview(request)[1], profile, today),
        "section": "assistant",
    })


@login_required
def symptom(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    form = SymptomForm(request.POST or None)
    analysis = save_url = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        analysis = analyze_symptom(vehicle, data["symptom"], data["description"], data["location"], data["severity"],
                                   timezone.localdate(), usage=profile_for(vehicle))
        save_url = f"{reverse('problem_create')}?" + urlencode({
            "sintoma": data["symptom"], "descricao": data["description"], "local": data["location"],
            "gravidade": data["severity"]})
    return render(request, "assistant/symptom.html", {
        "vehicle": vehicle, "form": form, "analysis": analysis, "save_url": save_url, "section": "assistant",
    })


@login_required
def problem_analysis(request, pk):
    problem = get_object_or_404(Problem.objects.select_related("vehicle"), pk=pk, vehicle__owner=request.user)
    analysis = analyze_problem(problem, timezone.localdate(), profile_for(problem.vehicle))
    return render(request, "assistant/problem_analysis.html", {
        "problem": problem, "vehicle": problem.vehicle, "analysis": analysis, "section": "assistant",
    })


@login_required
def usage_profile(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    profile = profile_for(vehicle) or UsageProfile(vehicle=vehicle)
    form = UsageProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil de uso salvo. As sugestões foram atualizadas.")
        return redirect("assistant_home")
    return render(request, "assistant/usage_profile.html", {"vehicle": vehicle, "form": form, "section": "assistant"})


@login_required
@require_POST
def add_tip(request, key):
    vehicle = get_active_vehicle(request)
    allowed = {item for keys, _ in USAGE_TIPS.values() for item in keys}
    if not vehicle or key not in allowed:
        return redirect("assistant_home")
    if add_suggestions(vehicle, [key]):
        messages.success(request, f"“{SUGGESTIONS_BY_KEY[key].title}” adicionado ao plano. Informe o intervalo do manual.")
    return redirect("assistant_home")


@login_required
def mechanic_summary(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    today = timezone.localdate()
    profile = profile_for(vehicle)
    data = review(vehicle, planning_overview(request)[1], profile, today)
    problems = [(problem, analysis, list(problem.updates.all())) for problem, analysis in data["problems"]]
    return render(request, "assistant/mechanic_summary.html", {
        "vehicle": vehicle, "review": data, "problems": problems, "today": today, "profile": profile,
        "latest": vehicle.latest_reading, "services": vehicle.services.prefetch_related("parts")[:8],
        "usage_labels": profile.labels if profile else [], "section": "assistant",
    })
