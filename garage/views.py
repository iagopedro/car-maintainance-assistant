from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.vary import vary_on_headers
from django.views.decorators.http import require_POST

from maintenance.models import Problem
from planning.alerts import planning_overview

from .context import ACTIVE_VEHICLE_KEY, get_active_vehicle
from .forms import LoginForm, ReadingFilterForm, ReadingForm, SetupForm, VehicleCreateForm, VehicleForm
from .models import Installation, OdometerReading, Vehicle
from .presets import load_local_preset
from .services import record_reading


class OwnerLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if not get_user_model().objects.exists():
            return redirect("setup")
        return super().dispatch(request, *args, **kwargs)


def setup(request):
    if get_user_model().objects.exists() or Installation.objects.exists():
        return redirect("login")
    if request.META.get("REMOTE_ADDR") not in {"127.0.0.1", "::1"}:
        return HttpResponseForbidden("A primeira conta deve ser criada neste computador, via localhost.")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                owner = form.save()
                Installation.objects.create(pk=1, owner=owner)
        except IntegrityError:
            return redirect("login")
        login(request, owner, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("dashboard")
    return render(request, "registration/setup.html", {"form": form})


def owned_vehicle(request, pk):
    return get_object_or_404(Vehicle, pk=pk, owner=request.user)


@login_required
def dashboard(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return render(request, "garage/dashboard.html", {"section": "dashboard"})
    today = timezone.localdate()
    latest = vehicle.latest_reading
    services = vehicle.services.all()
    active_problems = vehicle.problems.filter(status__in=Problem.ACTIVE_STATUSES)
    _, plans, alerts = planning_overview(request)
    context = {
        "section": "dashboard", "vehicle": vehicle, "latest": latest,
        "recent_services": services[:4], "service_count": services.count(),
        "active_problems": active_problems[:4], "active_problem_count": active_problems.count(),
        "plan_attention": sum(1 for plan in plans if plan.due.state in ("overdue", "soon")),
        "plan_count": len(plans), "alerts": alerts,
        "reading_age": (today - latest.date).days if latest else None,
    }
    return render(request, "garage/dashboard.html", context)


@login_required
def vehicle_list(request):
    vehicles = Vehicle.objects.filter(owner=request.user).prefetch_related("readings")
    return render(request, "garage/vehicle_list.html", {"vehicles": vehicles, "section": "garage"})


@login_required
def vehicle_create(request):
    initial = {}
    if request.GET.get("preset") == "exemplo":
        initial = {
            "brand": "Exemplo", "model": "Compacto", "model_year": 2022, "engine": "1.0 Flex",
            "notes": "Motorização e combustível a confirmar na documentação.",
            **load_local_preset("exemplo"),
        }
    form = VehicleCreateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            vehicle = form.save(commit=False)
            vehicle.owner = request.user
            vehicle.save()
            if form.cleaned_data.get("initial_kilometers") is not None:
                record_reading(owner=request.user, vehicle_id=vehicle.pk, date=form.cleaned_data["reading_date"],
                               kilometers=form.cleaned_data["initial_kilometers"], source=OdometerReading.Source.PANEL)
        request.session[ACTIVE_VEHICLE_KEY] = vehicle.pk
        messages.success(request, "Veículo cadastrado.")
        return redirect("vehicle_detail", pk=vehicle.pk)
    return render(request, "garage/vehicle_form.html", {"form": form, "creating": True, "section": "garage"})


@login_required
def vehicle_edit(request, pk):
    vehicle = owned_vehicle(request, pk)
    form = VehicleForm(request.POST or None, instance=vehicle)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados do veículo atualizados.")
        return redirect("vehicle_detail", pk=vehicle.pk)
    return render(request, "garage/vehicle_form.html", {"form": form, "vehicle": vehicle, "section": "garage"})


@login_required
def vehicle_detail(request, pk):
    vehicle = owned_vehicle(request, pk)
    return render(request, "garage/vehicle_detail.html", {
        "vehicle": vehicle, "latest": vehicle.latest_reading, "section": "garage",
    })


@login_required
@require_POST
def vehicle_activate(request, pk):
    vehicle = owned_vehicle(request, pk)
    request.session[ACTIVE_VEHICLE_KEY] = vehicle.pk
    return redirect("dashboard")


@login_required
@require_POST
def vehicle_switch(request):
    vehicle = get_object_or_404(Vehicle, pk=request.POST.get("vehicle") or 0, owner=request.user)
    request.session[ACTIVE_VEHICLE_KEY] = vehicle.pk
    target = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect("dashboard")


@login_required
@vary_on_headers("HX-Request")
def reading_list(request, pk):
    vehicle = owned_vehicle(request, pk)
    readings = vehicle.readings.all()
    form = ReadingFilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("start"):
            readings = readings.filter(date__gte=form.cleaned_data["start"])
        if form.cleaned_data.get("end"):
            readings = readings.filter(date__lte=form.cleaned_data["end"])
        if form.cleaned_data.get("source"):
            readings = readings.filter(source=form.cleaned_data["source"])
    else:
        readings = readings.none()
    page = Paginator(readings, 20).get_page(request.GET.get("page"))
    parameters = request.GET.copy()
    parameters.pop("page", None)
    context = {"vehicle": vehicle, "page_obj": page, "filter_form": form,
               "querystring": parameters.urlencode(), "section": "garage"}
    template = "garage/reading_results.html" if request.headers.get("HX-Request") == "true" else "garage/reading_list.html"
    return render(request, template, context)


@login_required
def reading_create(request, pk):
    vehicle = owned_vehicle(request, pk)
    form = ReadingForm(request.POST or None, instance=OdometerReading(vehicle=vehicle))
    if request.method == "POST" and form.is_valid():
        try:
            record_reading(owner=request.user, vehicle_id=vehicle.pk, **form.cleaned_data)
        except ValidationError as error:
            for field, errors in error.message_dict.items():
                form.add_error(field if field in form.fields else None, errors)
        except IntegrityError:
            form.add_error(None, "Já existe uma leitura nesta data. Confira o histórico.")
        else:
            messages.success(request, "Leitura registrada. O histórico foi preservado.")
            return redirect("reading_list", pk=vehicle.pk)
    return render(request, "garage/reading_form.html", {
        "form": form, "vehicle": vehicle, "latest": vehicle.latest_reading, "section": "garage",
    })