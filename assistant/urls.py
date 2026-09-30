from django.urls import path

from . import views

urlpatterns = [
    path("assistente/", views.home, name="assistant_home"),
    path("assistente/sintoma/", views.symptom, name="assistant_symptom"),
    path("assistente/problema/<int:pk>/", views.problem_analysis, name="assistant_problem"),
    path("assistente/perfil/", views.usage_profile, name="assistant_profile"),
    path("assistente/sugestao/<slug:key>/", views.add_tip, name="assistant_add_tip"),
    path("assistente/resumo/", views.mechanic_summary, name="assistant_summary"),
]
