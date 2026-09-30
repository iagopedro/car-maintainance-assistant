from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from assistant.engine import analyze_problem
from garage.context import get_active_vehicle
from planning.models import MaintenancePlan

from .attachments import save_attachments
from .forms import (LOCATION_SUGGESTIONS, SERVICE_SUGGESTIONS, AttachmentUploadForm, PartFormSet, ProblemFilterForm,
                    ProblemForm, ProblemUpdateForm, ServiceFilterForm, ServiceForm)
from .models import Attachment, Problem, ServiceRecord
from .services import add_problem_update, delete_service, save_problem, save_service


def km(value):
    return f"{value:,}".replace(",", ".")


def active_vehicle_or_redirect(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        messages.info(request, "Cadastre um veículo para começar.")
    return vehicle


def owned_service(request, pk):
    return get_object_or_404(ServiceRecord.objects.select_related("vehicle"), pk=pk, vehicle__owner=request.user)


def owned_problem(request, pk):
    return get_object_or_404(Problem.objects.select_related("vehicle", "resolved_by_service"), pk=pk,
                             vehicle__owner=request.user)


def paginate(request, queryset):
    parameters = request.GET.copy()
    parameters.pop("page", None)
    return Paginator(queryset, 20).get_page(request.GET.get("page")), parameters.urlencode()


def map_validation_error(form, error):
    for field, errors in error.message_dict.items():
        form.add_error(field if field in form.fields else None, errors)


@login_required
def register(request):
    vehicle = get_active_vehicle(request)
    return render(request, "maintenance/register.html", {"vehicle": vehicle, "section": "register"})


@login_required
@vary_on_headers("HX-Request")
def service_list(request):
    vehicle = active_vehicle_or_redirect(request)
    if not vehicle:
        return redirect("vehicle_create")
    services = vehicle.services.prefetch_related("parts")
    form = ServiceFilterForm(request.GET)
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            services = services.filter(Q(title__icontains=data["q"]) | Q(description__icontains=data["q"])
                                       | Q(workshop__icontains=data["q"]) | Q(notes__icontains=data["q"])
                                       | Q(parts__name__icontains=data["q"]) | Q(parts__brand_model__icontains=data["q"])).distinct()
        if data["category"]:
            services = services.filter(category=data["category"])
        if data["start"]:
            services = services.filter(date__gte=data["start"])
        if data["end"]:
            services = services.filter(date__lte=data["end"])
    else:
        services = services.none()
    totals = ServiceRecord.objects.filter(pk__in=services.values("pk")).aggregate(
        total=Sum("total_cost"), unpriced=Count("pk", filter=Q(total_cost__isnull=True)))
    page, querystring = paginate(request, services)
    context = {"vehicle": vehicle, "page_obj": page, "filter_form": form, "querystring": querystring,
               "totals": totals, "section": "services"}
    template = "maintenance/service_results.html" if request.headers.get("HX-Request") == "true" else "maintenance/service_list.html"
    return render(request, template, context)


def service_form_view(request, vehicle, service):
    creating = service.pk is None
    initial = {}
    if creating:
        initial["date"] = timezone.localdate()
        problem_id = request.GET.get("problema")
        if problem_id and problem_id.isdigit():
            initial["resolves"] = problem_id
            initial["kind"] = ServiceRecord.Kind.CORRECTIVE
        plan = getattr(request, "_linked_plan", None)
        if plan:
            initial.update(plan=plan.pk, title=plan.title, category=plan.category,
                           kind=ServiceRecord.Kind.INSPECTION if plan.kind == "inspection" else ServiceRecord.Kind.PREVENTIVE)
    data = (request.POST, request.FILES) if request.method == "POST" else (None, None)
    form = ServiceForm(*data, instance=service, vehicle=vehicle, initial=initial)
    parts = PartFormSet(*data, instance=service, prefix="parts")
    if request.method == "POST" and form.is_valid() and parts.is_valid():
        previous_reading = vehicle.latest_reading
        try:
            service = save_service(owner=request.user, form=form, parts=parts)
        except ValidationError as error:
            map_validation_error(form, error)
        else:
            messages.success(request, "Serviço registrado." if creating else "Serviço atualizado.")
            outcome, day_km = service.reading_outcome or (None, None)
            day = service.date.strftime("%d/%m/%Y") if service.date else ""
            latest = service.vehicle.latest_reading
            if outcome == "kept":
                messages.warning(request, f"Já existe uma leitura de {km(day_km)} km em {day}. A quilometragem do "
                                          f"serviço ({km(service.kilometers)} km) não foi usada no histórico de km.")
            elif outcome == "replaced" and latest and latest.pk == service.odometer_reading_id:
                messages.success(request, f"Quilometragem atual atualizada para {km(latest.kilometers)} km "
                                          f"(substitui a leitura de {km(day_km)} km do mesmo dia).")
            elif outcome == "replaced":
                messages.success(request, f"Leitura de {day} atualizada para {km(service.kilometers)} km "
                                          f"(substitui {km(day_km)} km).")
            elif latest and latest.pk == service.odometer_reading_id and latest != previous_reading:
                messages.success(request, f"Quilometragem atual atualizada para {km(latest.kilometers)} km.")
            return redirect("service_detail", pk=service.pk)
    workshops = vehicle.services.exclude(workshop="").values_list("workshop", flat=True).distinct().order_by("workshop")[:50]
    return render(request, "maintenance/service_form.html", {
        "form": form, "parts": parts, "vehicle": vehicle, "service": service, "creating": creating,
        "service_suggestions": SERVICE_SUGGESTIONS, "workshops": workshops, "section": "services",
    })


@login_required
def service_create(request):
    problem_id = request.GET.get("problema", "")
    plan_id = request.GET.get("plano", "")
    if problem_id.isdigit():
        vehicle = owned_problem(request, int(problem_id)).vehicle
    elif plan_id.isdigit():
        request._linked_plan = get_object_or_404(MaintenancePlan, pk=int(plan_id), vehicle__owner=request.user)
        vehicle = request._linked_plan.vehicle
    else:
        vehicle = active_vehicle_or_redirect(request)
    if not vehicle:
        return redirect("vehicle_create")
    return service_form_view(request, vehicle, ServiceRecord(vehicle=vehicle))


@login_required
def service_edit(request, pk):
    service = owned_service(request, pk)
    return service_form_view(request, service.vehicle, service)


@login_required
def service_detail(request, pk):
    service = owned_service(request, pk)
    return render(request, "maintenance/service_detail.html", {
        "service": service, "vehicle": service.vehicle, "parts": service.parts.all(),
        "attachments": service.attachments.all(), "resolved_problems": service.resolved_problems.all(),
        "upload_form": AttachmentUploadForm(), "section": "services",
    })


@login_required
def service_delete(request, pk):
    service = owned_service(request, pk)
    if request.method == "POST":
        delete_service(service)
        messages.success(request, "Serviço excluído.")
        return redirect("service_list")
    return render(request, "maintenance/confirm_delete.html", {
        "object_label": service.display_title, "kind": "serviço", "service": service, "section": "services",
    })


@login_required
@vary_on_headers("HX-Request")
def problem_list(request):
    vehicle = active_vehicle_or_redirect(request)
    if not vehicle:
        return redirect("vehicle_create")
    form = ProblemFilterForm(request.GET)
    problems = vehicle.problems.all()
    view = "active"
    if form.is_valid():
        view = form.cleaned_data["view"] or "active"
        if form.cleaned_data["q"]:
            q = form.cleaned_data["q"]
            problems = problems.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(location__icontains=q)
                                       | Q(diagnosis__icontains=q) | Q(solution__icontains=q) | Q(ruled_out__icontains=q))
    if view == "active":
        problems = problems.filter(status__in=Problem.ACTIVE_STATUSES)
    elif view == "closed":
        problems = problems.exclude(status__in=Problem.ACTIVE_STATUSES)
    page, querystring = paginate(request, problems)
    counts = vehicle.problems.aggregate(active=Count("pk", filter=Q(status__in=Problem.ACTIVE_STATUSES)), all=Count("pk"))
    context = {
        "vehicle": vehicle, "page_obj": page, "filter_form": form, "querystring": querystring, "view": view,
        "counts": counts, "views": ProblemFilterForm.VIEWS, "section": "problems",
    }
    template = "maintenance/problem_results.html" if request.headers.get("HX-Request") == "true" else "maintenance/problem_list.html"
    return render(request, template, context)


def problem_form_view(request, vehicle, problem, initial=None):
    creating = problem.pk is None
    data = (request.POST, request.FILES) if request.method == "POST" else (None, None)
    form = ProblemForm(*data, instance=problem, vehicle=vehicle, initial=initial or {})
    if request.method == "POST" and form.is_valid():
        problem = save_problem(form)
        messages.success(request, "Problema registrado." if creating else "Problema atualizado.")
        return redirect("problem_detail", pk=problem.pk)
    return render(request, "maintenance/problem_form.html", {
        "form": form, "vehicle": vehicle, "problem": problem, "creating": creating,
        "location_suggestions": LOCATION_SUGGESTIONS, "section": "problems",
    })


@login_required
def problem_create(request):
    vehicle = active_vehicle_or_redirect(request)
    if not vehicle:
        return redirect("vehicle_create")
    initial = {"reported_on": timezone.localdate()}
    if request.GET.get("descricao"):
        initial = {"reported_on": timezone.localdate(), "description": request.GET["descricao"][:2000],
                   "location": request.GET.get("local", "")[:120]}
        if request.GET.get("sintoma") in Problem.Symptom.values:
            initial["symptom"] = request.GET["sintoma"]
        if request.GET.get("gravidade") in Problem.Severity.values:
            initial["severity"] = request.GET["gravidade"]
    return problem_form_view(request, vehicle, Problem(vehicle=vehicle), initial)


@login_required
def problem_edit(request, pk):
    problem = owned_problem(request, pk)
    return problem_form_view(request, problem.vehicle, problem)


@login_required
def problem_detail(request, pk):
    problem = owned_problem(request, pk)
    form = ProblemUpdateForm(request.POST or None, problem=problem)
    if request.method == "POST" and form.is_valid():
        add_problem_update(problem, form)
        messages.success(request, "Acompanhamento registrado.")
        return redirect("problem_detail", pk=problem.pk)
    return render(request, "maintenance/problem_detail.html", {
        "problem": problem, "vehicle": problem.vehicle, "updates": problem.updates.all(), "update_form": form,
        "attachments": problem.attachments.all(), "upload_form": AttachmentUploadForm(), "section": "problems",
        "analysis": analyze_problem(problem, timezone.localdate()) if problem.is_active else None,
    })


@login_required
def problem_delete(request, pk):
    problem = owned_problem(request, pk)
    if request.method == "POST":
        problem.delete()
        messages.success(request, "Problema excluído.")
        return redirect("problem_list")
    return render(request, "maintenance/confirm_delete.html", {
        "object_label": problem.display_title, "kind": "problema", "problem": problem, "section": "problems",
    })


def owned_attachments(request):
    return Attachment.objects.filter(Q(service__vehicle__owner=request.user) | Q(problem__vehicle__owner=request.user))


def attachment_parent_url(attachment):
    if attachment.service_id:
        return redirect("service_detail", pk=attachment.service_id)
    return redirect("problem_detail", pk=attachment.problem_id)


@login_required
@require_POST
def attachment_upload(request, kind, pk):
    parent = owned_service(request, pk) if kind == "servico" else owned_problem(request, pk)
    form = AttachmentUploadForm(request.POST, request.FILES)
    if form.is_valid():
        target = {"service": parent} if kind == "servico" else {"problem": parent}
        count = save_attachments(form.cleaned_data["attachments"], **target)
        messages.success(request, f"{count} anexo{'s' if count > 1 else ''} adicionado{'s' if count > 1 else ''}.")
    else:
        for error in form.errors.get("attachments", []):
            messages.error(request, error)
    return redirect("service_detail" if kind == "servico" else "problem_detail", pk=parent.pk)


@login_required
def attachment_file(request, pk):
    attachment = get_object_or_404(owned_attachments(request), pk=pk)
    try:
        handle = attachment.file.open("rb")
    except FileNotFoundError as error:
        raise Http404("Arquivo não encontrado.") from error
    inline = attachment.is_image and request.GET.get("baixar") != "1"
    response = FileResponse(handle, content_type=attachment.content_type, as_attachment=not inline,
                            filename=attachment.original_name)
    response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; sandbox"
    return response


@login_required
@require_POST
def attachment_delete(request, pk):
    attachment = get_object_or_404(owned_attachments(request), pk=pk)
    response = attachment_parent_url(attachment)
    attachment.delete()
    messages.success(request, "Anexo removido.")
    return response
