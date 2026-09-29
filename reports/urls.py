from django.urls import path

from . import views

urlpatterns = [
    path("historico/", views.timeline, name="timeline"),
    path("financas/", views.finance, name="finance"),
    path("dados/", views.data_home, name="data_home"),
    path("dados/csv/<slug:kind>/", views.export_csv, name="export_csv"),
    path("dados/backup/", views.download_backup, name="download_backup"),
    path("dados/restaurar/", views.restore, name="restore_backup"),
    path("mais/", views.more, name="more"),
]
