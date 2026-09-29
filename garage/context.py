from .models import Vehicle

ACTIVE_VEHICLE_KEY = "active_vehicle_id"


def get_active_vehicle(request):
    if not request.user.is_authenticated:
        return None
    if not hasattr(request, "_active_vehicle"):
        vehicles = Vehicle.objects.filter(owner=request.user)
        request._active_vehicle = (
            vehicles.filter(pk=request.session.get(ACTIVE_VEHICLE_KEY)).first() or vehicles.first()
        )
    return request._active_vehicle


def active_vehicle(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "active_vehicle": get_active_vehicle(request),
        "owner_vehicles": Vehicle.objects.filter(owner=request.user),
    }
