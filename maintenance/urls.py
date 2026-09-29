from django.urls import path

from . import views

urlpatterns = [
    path("registrar/", views.register, name="register"),
    path("servicos/", views.service_list, name="service_list"),
    path("servicos/novo/", views.service_create, name="service_create"),
    path("servicos/<int:pk>/", views.service_detail, name="service_detail"),
    path("servicos/<int:pk>/editar/", views.service_edit, name="service_edit"),
    path("servicos/<int:pk>/excluir/", views.service_delete, name="service_delete"),
    path("problemas/", views.problem_list, name="problem_list"),
    path("problemas/novo/", views.problem_create, name="problem_create"),
    path("problemas/<int:pk>/", views.problem_detail, name="problem_detail"),
    path("problemas/<int:pk>/editar/", views.problem_edit, name="problem_edit"),
    path("problemas/<int:pk>/excluir/", views.problem_delete, name="problem_delete"),
    path("servicos/<int:pk>/anexos/", views.attachment_upload, {"kind": "servico"}, name="service_attachment_upload"),
    path("problemas/<int:pk>/anexos/", views.attachment_upload, {"kind": "problema"}, name="problem_attachment_upload"),
    path("anexos/<int:pk>/", views.attachment_file, name="attachment_file"),
    path("anexos/<int:pk>/excluir/", views.attachment_delete, name="attachment_delete"),
]
