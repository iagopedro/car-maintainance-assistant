import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import OdometerReading, Vehicle
from .services import record_reading


class OdometerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="owner")
        cls.other = get_user_model().objects.create_user(username="other")
        cls.vehicle = Vehicle.objects.create(owner=cls.owner, brand="Exemplo", model="Compacto", model_year=2022)

    def record(self, days, kilometers, **kwargs):
        return record_reading(owner=kwargs.get("owner", self.owner), vehicle_id=self.vehicle.pk,
                              date=timezone.localdate() - timedelta(days=days), kilometers=kilometers,
                              source=OdometerReading.Source.PANEL)

    def test_unknown_odometer_is_not_zero(self):
        self.assertIsNone(self.vehicle.latest_reading)

    def test_retroactive_reading_does_not_replace_latest(self):
        self.record(0, 45000)
        self.record(20, 44000)
        self.assertEqual(self.vehicle.latest_reading.kilometers, 45000)

    def test_reject_decrease(self):
        self.record(20, 44000)
        with self.assertRaises(ValidationError):
            self.record(0, 43000)

    def test_reject_retroactive_reading_above_later(self):
        self.record(0, 45000)
        with self.assertRaises(ValidationError):
            self.record(20, 46000)

    def test_reject_duplicate_day(self):
        self.record(0, 45000)
        with self.assertRaises(ValidationError):
            self.record(0, 45001)

    def test_accept_same_mileage_on_different_days(self):
        self.record(1, 45000)
        self.record(0, 45000)
        self.assertEqual(self.vehicle.readings.count(), 2)

    def test_reject_future_negative_and_excessive_readings(self):
        for days, kilometers in [(-1, 45000), (0, -1), (0, 10000000)]:
            with self.subTest(days=days, kilometers=kilometers), self.assertRaises(ValidationError):
                self.record(days, kilometers)

    def test_other_owner_cannot_record(self):
        with self.assertRaises(Vehicle.DoesNotExist):
            self.record(0, 45000, owner=self.other)

    def test_vehicle_validation(self):
        self.vehicle.acquisition_date = timezone.localdate() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.vehicle.full_clean()


class GarageWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="driver", password="A-test-only-password-947!")
        cls.other = get_user_model().objects.create_user(username="other")
        cls.vehicle = Vehicle.objects.create(owner=cls.owner, brand="Exemplo", model="Compacto", model_year=2022)
        cls.foreign_vehicle = Vehicle.objects.create(owner=cls.other, brand="Other", model="Private", model_year=2021)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_pages_render(self):
        paths = ["/", "/veiculos/", "/veiculos/novo/", "/veiculos/novo/?preset=exemplo", "/conta/senha/",
                 f"/veiculos/{self.vehicle.pk}/", f"/veiculos/{self.vehicle.pk}/editar/",
                 f"/veiculos/{self.vehicle.pk}/quilometragem/", f"/veiculos/{self.vehicle.pk}/quilometragem/nova/"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_unauthenticated_access_redirects(self):
        self.client.logout()
        self.assertRedirects(self.client.get("/"), "/conta/entrar/?next=/")

    def test_owner_isolation_for_all_vehicle_endpoints(self):
        for suffix in ["", "editar/", "quilometragem/", "quilometragem/nova/", "ativar/"]:
            with self.subTest(suffix=suffix):
                path = f"/veiculos/{self.foreign_vehicle.pk}/{suffix}"
                self.assertEqual(self.client.post(path, {}).status_code, 404)
        self.assertNotContains(self.client.get("/veiculos/"), "Private")

    def test_create_vehicle_with_unknown_mileage(self):
        response = self.client.post("/veiculos/novo/", {"brand": "Exemplo", "model": "Compacto", "model_year": 2022, "fuel": "unknown"})
        self.assertEqual(response.status_code, 302)
        vehicle = Vehicle.objects.order_by("-pk").first()
        self.assertEqual(vehicle.owner, self.owner)
        self.assertIsNone(vehicle.latest_reading)
        self.assertEqual(self.client.session["active_vehicle_id"], vehicle.pk)

    def test_create_vehicle_with_zero_mileage(self):
        response = self.client.post("/veiculos/novo/", {"brand": "Exemplo", "model": "Compacto", "model_year": 2022, "fuel": "flex",
                                   "initial_kilometers": 0, "reading_date": timezone.localdate().isoformat()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vehicle.objects.order_by("-pk").first().latest_reading.kilometers, 0)

    def test_invalid_initial_reading_does_not_create_vehicle(self):
        count = Vehicle.objects.count()
        response = self.client.post("/veiculos/novo/", {"brand": "Exemplo", "model": "Compacto", "model_year": 2022,
                                   "fuel": "flex", "initial_kilometers": 1000})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vehicle.objects.count(), count)

    def test_owner_cannot_be_changed_by_form(self):
        self.client.post(f"/veiculos/{self.vehicle.pk}/editar/", {"brand": "Exemplo", "model": "Compacto", "model_year": 2022,
                         "fuel": "flex", "owner": self.other.pk})
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.owner, self.owner)

    def test_add_reading_duplicate_and_filters(self):
        path = f"/veiculos/{self.vehicle.pk}/quilometragem/"
        data = {"date": timezone.localdate().isoformat(), "kilometers": 40000, "source": "panel", "notes": "Teste"}
        self.assertRedirects(self.client.post(path + "nova/", data), path)
        self.assertEqual(self.client.post(path + "nova/", data).status_code, 200)
        self.assertEqual(self.vehicle.readings.count(), 1)
        self.assertContains(self.client.get(path), "40.000")
        self.assertNotContains(self.client.get(path, {"source": "document"}), "40.000")
        self.assertContains(self.client.get(path, {"start": "2022-05-10", "end": "2022-01-01"}), "data inicial")
        self.assertContains(self.client.get(path, {"start": "invalid"}), "data válida")
        self.assertNotContains(self.client.get(path, HTTP_HX_REQUEST="true"), "<!doctype")

    def test_active_vehicle_and_stale_session(self):
        self.assertEqual(self.client.get(f"/veiculos/{self.vehicle.pk}/ativar/").status_code, 405)
        self.client.post(f"/veiculos/{self.vehicle.pk}/ativar/")
        self.assertEqual(self.client.session["active_vehicle_id"], self.vehicle.pk)
        session = self.client.session
        session["active_vehicle_id"] = self.foreign_vehicle.pk
        session.save()
        self.assertNotContains(self.client.get("/"), "Private")

    def test_csrf_required(self):
        from django.test import Client
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.post(f"/veiculos/{self.vehicle.pk}/ativar/").status_code, 403)

    def test_notes_are_escaped(self):
        self.vehicle.notes = '<script>alert("unsafe")</script>'
        self.vehicle.save()
        response = self.client.get(f"/veiculos/{self.vehicle.pk}/")
        self.assertNotContains(response, '<script>alert("unsafe")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_accessible_vehicle_switching(self):
        second = Vehicle.objects.create(owner=self.owner, brand="Honda", model="Fit", model_year=2015)
        self.client.post(f"/veiculos/{second.pk}/ativar/")
        dashboard = self.client.get("/")
        self.assertNotContains(dashboard, "data-autosubmit")
        self.assertContains(dashboard, 'Trocar<span class="visually-hidden"> veículo ativo</span>', html=False)
        garage = self.client.get("/veiculos/")
        self.assertContains(garage, f'Usar no painel<span class="visually-hidden"> ({self.vehicle})</span>')
        self.assertNotContains(garage, f'Usar no painel<span class="visually-hidden"> ({second})</span>')
        self.assertContains(garage, "No painel")
        self.assertContains(garage, '<span class="visually-hidden"> veículos</span>')

    def test_vehicle_without_notes_or_engine(self):
        response = self.client.get(f"/veiculos/{self.vehicle.pk}/")
        self.assertContains(response, "Sem observações.")
        self.assertNotContains(response, "A confirmar</span>")
        self.assertNotContains(self.client.get("/"), "Motorização a confirmar")

    def test_login_logout_and_rate_limit(self):
        self.client.logout()
        response = self.client.post("/conta/entrar/", {"username": "driver", "password": "A-test-only-password-947!"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/conta/sair/").status_code, 405)
        self.assertEqual(self.client.post("/conta/sair/").status_code, 302)
        for attempt in range(5):
            response = self.client.post("/conta/entrar/", {"username": "driver", "password": "wrong"})
        self.assertEqual(response.status_code, 429)


class SetupTests(TestCase):
    def test_setup_is_local_only(self):
        self.assertEqual(self.client.get("/conta/iniciar/", REMOTE_ADDR="192.168.1.2").status_code, 403)

    def test_setup_creates_only_first_owner(self):
        response = self.client.post("/conta/iniciar/", {"username": "driver", "password1": "Local-test-setup-947!",
                                   "password2": "Local-test-setup-947!"})
        self.assertRedirects(response, "/")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(self.client.get("/conta/iniciar/").status_code, 302)

    def test_empty_installation_routes_to_setup(self):
        self.assertRedirects(self.client.get("/conta/entrar/"), "/conta/iniciar/")

    def test_weak_password_rejected(self):
        response = self.client.post("/conta/iniciar/", {"username": "driver", "password1": "123", "password2": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.exists())


class LocalPresetTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="owner"))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.presets = Path(directory.name) / "presets.json"
        override = override_settings(LOCAL_PRESETS_FILE=self.presets)
        override.enable()
        self.addCleanup(override.disable)

    def test_missing_file_keeps_generic_preset(self):
        response = self.client.get("/veiculos/novo/?preset=exemplo")
        self.assertContains(response, "Motorização e combustível a confirmar")

    def test_local_notes_are_used_and_unknown_fields_ignored(self):
        self.presets.write_text(json.dumps({"exemplo": {"notes": "Uso local privado", "owner": 999}}), encoding="utf-8")
        response = self.client.get("/veiculos/novo/?preset=exemplo")
        self.assertContains(response, "Uso local privado")

    def test_invalid_file_is_ignored(self):
        self.presets.write_text("{invalid", encoding="utf-8")
        self.assertEqual(self.client.get("/veiculos/novo/?preset=exemplo").status_code, 200)