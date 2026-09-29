from django.db import transaction
from django.utils import timezone

from garage.models import OdometerReading, Vehicle

from .attachments import save_attachments
from .models import Problem, ProblemUpdate

CLOSED_STATUSES = {Problem.Status.RESOLVED, Problem.Status.CLOSED}


def sync_service_reading(service):
    """Mirror the service odometer into the vehicle history; returns a reading that must be deleted, if any."""
    own = service.odometer_reading
    same_day_exists = service.date and service.vehicle.readings.filter(date=service.date).exclude(
        pk=own.pk if own else None).exists()
    if service.date is None or service.kilometers is None or same_day_exists:
        service.odometer_reading = None
        return own
    reading = own or OdometerReading(vehicle=service.vehicle, source=OdometerReading.Source.SERVICE)
    reading.date, reading.kilometers = service.date, service.kilometers
    reading.notes = f"Registrada pelo serviço: {service.display_title}"[:500]
    reading.full_clean()
    reading.save()
    service.odometer_reading = reading
    return None


def resolve_with_service(problem, service):
    problem.status = Problem.Status.RESOLVED
    problem.resolved_on = service.date
    problem.resolved_by_service = service
    if not problem.solution:
        problem.solution = f"Resolvido pelo serviço: {service.display_title}."
    problem.save()
    ProblemUpdate.objects.create(problem=problem, date=service.date or timezone.localdate(),
                                 status=Problem.Status.RESOLVED, note=f"Resolvido pelo serviço “{service.display_title}”.")


@transaction.atomic
def save_service(*, owner, form, parts):
    service = form.save(commit=False)
    service.vehicle = Vehicle.objects.select_for_update().get(pk=service.vehicle_id, owner=owner)
    stale_reading = sync_service_reading(service)
    service.save()
    if stale_reading:
        stale_reading.delete()
    parts.instance = service
    parts.save()
    if form.cleaned_data.get("resolves"):
        resolve_with_service(form.cleaned_data["resolves"], service)
    save_attachments(form.cleaned_data.get("attachments") or [], service=service)
    return service


@transaction.atomic
def delete_service(service):
    reading = service.odometer_reading
    service.delete()
    if reading:
        reading.delete()


def apply_status(problem, status, when):
    problem.status = status
    if status in CLOSED_STATUSES:
        problem.resolved_on = problem.resolved_on or when
    else:
        problem.resolved_on = None


@transaction.atomic
def save_problem(form):
    creating = form.instance.pk is None
    previous_status = None if creating else form.initial.get("status")
    problem = form.save(commit=False)
    if problem.status not in CLOSED_STATUSES:
        problem.resolved_on = None
    problem.save()
    if previous_status and previous_status != problem.status:
        ProblemUpdate.objects.create(problem=problem, status=problem.status, note="Situação alterada na edição.")
    save_attachments(form.cleaned_data.get("attachments") or [], problem=problem)
    return problem


@transaction.atomic
def add_problem_update(problem, form):
    update = form.save(commit=False)
    update.problem = problem
    if update.status:
        apply_status(problem, update.status, update.date)
        if update.status == Problem.Status.RESOLVED and not problem.solution and update.note:
            problem.solution = update.note
        problem.save()
    update.save()
    return update
