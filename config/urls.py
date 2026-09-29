from django.urls import include, path


urlpatterns = [
    path("", include("garage.urls")),
    path("", include("maintenance.urls")),
    path("", include("planning.urls")),
    path("", include("reports.urls")),
]