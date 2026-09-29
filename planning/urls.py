from django.urls import path

from . import views

urlpatterns = [
    path("plano/", views.plan_list, name="plan_list"),
    path("plano/novo/", views.plan_create, name="plan_create"),
    path("plano/sugestoes/", views.suggestions, name="plan_suggestions"),
    path("plano/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("plano/<int:pk>/editar/", views.plan_edit, name="plan_edit"),
    path("plano/<int:pk>/excluir/", views.plan_delete, name="plan_delete"),
    path("plano/<int:pk>/<str:action>/", views.plan_action, name="plan_action"),
    path("alertas/", views.alert_list, name="alert_list"),
    path("alertas/configurar/", views.alert_settings, name="alert_settings"),
]
