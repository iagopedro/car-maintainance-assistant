from django.db import transaction

from .catalog import SUGGESTIONS_BY_KEY
from .models import MaintenancePlan

Status = MaintenancePlan.Status


def apply_completion(plan):
    if plan.status == Status.DISMISSED:
        return
    if plan.is_recurring:
        plan.next_km = plan.next_date = plan.scheduled_for = None
        plan.status = Status.PENDING
    else:
        plan.status = Status.DONE
    plan.save()


def refresh_after_unlink(plan):
    if plan.status == Status.DONE and not plan.is_recurring and not plan.services.exists():
        plan.status = Status.PENDING
        plan.save()


@transaction.atomic
def add_suggestions(vehicle, keys):
    existing = set(vehicle.plans.exclude(suggestion_key="").values_list("suggestion_key", flat=True))
    created = []
    for key in keys:
        if key in existing:
            continue
        suggestion = SUGGESTIONS_BY_KEY[key]
        created.append(MaintenancePlan.objects.create(
            vehicle=vehicle, title=suggestion.title, category=suggestion.category, kind=suggestion.kind,
            priority=suggestion.priority, reason=suggestion.reason, suggestion_key=key))
    return created


@transaction.atomic
def link_service(plan, service):
    service.plan = plan
    service.save(update_fields=["plan"])
    apply_completion(plan)


def schedule(plan, when):
    plan.status, plan.scheduled_for = Status.SCHEDULED, when
    plan.save()


def dismiss(plan, reason):
    plan.status, plan.dismissed_reason, plan.scheduled_for = Status.DISMISSED, reason, None
    plan.save()


def reactivate(plan):
    plan.status, plan.dismissed_reason, plan.scheduled_for = Status.PENDING, "", None
    plan.save()
