from django.urls import include, path


urlpatterns = [path("", include("garage.urls")), path("", include("maintenance.urls"))]