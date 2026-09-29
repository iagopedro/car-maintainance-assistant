from django.db import transaction
from django.db.models.functions import Now

from .models import OdometerReading, Vehicle


@transaction.atomic
def record_reading(*, owner, vehicle_id, date, kilometers, source, notes=""):
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id, owner=owner)
    Vehicle.objects.filter(pk=vehicle.pk).update(updated_at=Now())
    reading = OdometerReading(vehicle=vehicle, date=date, kilometers=kilometers, source=source, notes=notes)
    reading.full_clean()
    reading.save()
    return reading