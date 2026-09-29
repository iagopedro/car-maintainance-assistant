from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from garage.context import get_active_vehicle
from garage.models import Vehicle
from planning.alerts import planning_overview

from .backup import BackupError, create_backup, restore_backup
from .exports import EXPORTS, render_csv
from .finance import period_choices, summarize
from .forms import RestoreForm, TimelineFilterForm
from .models import BackupRecord
from .timeline import build_timeline


@login_required
@vary_on_headers("HX-Request")
def timeline(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    form = TimelineFilterForm(request.GET)
    filters = form.cleaned_data if form.is_valid() else {}
    upcoming, history = build_timeline(vehicle, planning_overview(request)[1], filters) if form.is_valid() else ([], [])
    page = Paginator(history, 40).get_page(request.GET.get("page"))
    parameters = request.GET.copy()
    parameters.pop("page", None)
    context = {"vehicle": vehicle, "form": form, "upcoming": upcoming[:6], "page_obj": page,
               "querystring": parameters.urlencode(), "section": "timeline",
               "filtered": any(request.GET.get(name) for name in ("type", "category", "status", "start", "end"))}
    template = "reports/timeline_results.html" if request.headers.get("HX-Request") == "true" else "reports/timeline.html"
    return render(request, template, context)


@login_required
def finance(request):
    vehicle = get_active_vehicle(request)
    if not vehicle:
        return redirect("vehicle_create")
    today = timezone.localdate()
    choices = period_choices(vehicle, today)
    period = request.GET.get("periodo", "12m")
    if period not in dict(choices):
        period = "12m"
    summary = summarize(vehicle, planning_overview(request)[1], period, today)
    return render(request, "reports/finance.html", {
        "vehicle": vehicle, "summary": summary, "choices": choices, "period": period,
        "period_label": dict(choices)[period], "section": "finance",
    })


@login_required
def data_home(request):
    return render(request, "reports/data.html", {
        "exports": [(key, label) for key, (label, _) in EXPORTS.items()],
        "last_backup": BackupRecord.objects.filter(owner=request.user).first(),
        "can_restore": not Vehicle.objects.filter(owner=request.user).exists(),
        "restore_form": RestoreForm(), "section": "data",
    })


@login_required
def export_csv(request, kind):
    if kind not in EXPORTS:
        raise Http404
    label, rows = EXPORTS[kind]
    response = HttpResponse(render_csv(rows(request.user)), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="rodagem-{kind}-{timezone.localdate():%Y-%m-%d}.csv"'
    return response


@login_required
@require_POST
def download_backup(request):
    handle, size, missing = create_backup(request.user)
    BackupRecord.objects.create(owner=request.user, size=size, source=BackupRecord.Source.WEB)
    if missing:
        messages.error(request, f"{missing} anexo(s) não foram encontrados no disco e ficaram fora do backup.")
    filename = f"rodagem-backup-{timezone.localtime():%Y-%m-%d-%H%M}.zip"
    return FileResponse(handle, as_attachment=True, filename=filename, content_type="application/zip")


@login_required
@require_POST
def restore(request):
    form = RestoreForm(request.POST, request.FILES)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("data_home")
    try:
        counts = restore_backup(request.user, form.cleaned_data["backup"])
    except BackupError as error:
        messages.error(request, str(error))
        return redirect("data_home")
    request.session.pop("active_vehicle_id", None)
    messages.success(request, f"Backup restaurado: {counts['vehicles']} veículo(s), {counts['services']} serviço(s), "
                              f"{counts['problems']} problema(s), {counts['plans']} item(ns) do plano e "
                              f"{counts['attachments']} anexo(s).")
    return redirect("dashboard")


@login_required
def more(request):
    return render(request, "reports/more.html", {"section": "more"})
