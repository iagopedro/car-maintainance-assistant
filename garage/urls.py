from django.contrib.auth.views import LogoutView, PasswordChangeView, PasswordChangeDoneView
from django.urls import path, reverse_lazy

from . import views
from .forms import OwnerPasswordChangeForm


urlpatterns = [
	path("", views.dashboard, name="dashboard"),
	path("conta/iniciar/", views.setup, name="setup"),
	path("conta/entrar/", views.OwnerLoginView.as_view(), name="login"),
	path("conta/sair/", LogoutView.as_view(), name="logout"),
	path("conta/senha/", PasswordChangeView.as_view(template_name="registration/password_change.html",
		    form_class=OwnerPasswordChangeForm,
		 success_url=reverse_lazy("password_change_done")), name="password_change"),
	path("conta/senha/alterada/", PasswordChangeDoneView.as_view(template_name="registration/password_done.html"), name="password_change_done"),
	path("veiculos/", views.vehicle_list, name="vehicle_list"),
	path("veiculos/novo/", views.vehicle_create, name="vehicle_create"),
	path("veiculos/<int:pk>/", views.vehicle_detail, name="vehicle_detail"),
	path("veiculos/<int:pk>/editar/", views.vehicle_edit, name="vehicle_edit"),
	path("veiculos/<int:pk>/ativar/", views.vehicle_activate, name="vehicle_activate"),    path("veiculos/trocar/", views.vehicle_switch, name="vehicle_switch"),	path("veiculos/<int:pk>/quilometragem/", views.reading_list, name="reading_list"),
	path("veiculos/<int:pk>/quilometragem/nova/", views.reading_create, name="reading_create"),
]