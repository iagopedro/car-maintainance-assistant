import io
import json
import shutil
import tempfile
import zipfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from assistant.models import UsageProfile
from garage.models import OdometerReading, Vehicle
from maintenance.models import Attachment, Problem, ProblemUpdate, ServicePart, ServiceRecord
from planning.models import AlertPreferences, MaintenancePlan

from .backup import BackupError, create_backup, restore_backup
from .exports import cell, render_csv, services
from .finance import period_bounds, summarize
from .models import BackupRecord

PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 64
TODAY = timezone.localdate


class ReportTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_root = tempfile.mkdtemp()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="owner")
        cls.other = user_model.objects.create_user(username="other")
        cls.vehicle = Vehicle.objects.create(owner=cls.owner, brand="Exemplo", model="Compacto", model_year=2022)
        cls.foreign = Vehicle.objects.create(owner=cls.other, brand="Other", model="Private", model_year=2020)

    def setUp(self):
        self.client.force_login(self.owner)

    def service(self, days_ago, total, category="oil", kind="preventive", vehicle=None, **fields):
        day = TODAY() - timedelta(days=days_ago) if days_ago is not None else None
        return ServiceRecord.objects.create(vehicle=vehicle or self.vehicle, category=category, kind=kind, date=day,
                                            total_cost=Decimal(total) if total is not None else None, **fields)


class TimelineTests(ReportTestCase):
    def test_entries_filters_and_grouping(self):
        oil = self.service(10, "150", title="Troca de óleo", workshop="Oficina A")
        ServicePart.objects.create(service=oil, name="Filtro")
        self.service(40, "300", category="suspension", kind="corrective", title="Bandeja")
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Barulho na porta",
                                         reported_on=TODAY() - timedelta(days=5), category="body")
        ProblemUpdate.objects.create(problem=problem, date=TODAY(), status="resolved", note="Drenado")
        Problem.objects.create(vehicle=self.vehicle, symptom="leak", description="Sem data")
        OdometerReading.objects.create(vehicle=self.vehicle, date=TODAY() - timedelta(days=2), kilometers=45000)
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Fluido de freio", next_date=TODAY() + timedelta(days=20))
        self.service(None, None, category="audio", title="Som antigo")
        response = self.client.get("/historico/")
        for text in ("Troca de óleo", "Peças: Filtro", "R$ 150,00", "Relato: Barulho na porta", "Resolvido: Barulho",
                     "45.000 km", "Pela frente", "Fluido de freio", "Data desconhecida", "Som antigo"):
            self.assertContains(response, text)
        content = response.content.decode()
        self.assertLess(content.index("Resolvido: Barulho"), content.index("Troca de óleo"))
        self.assertLess(content.index("Bandeja"), content.index("Som antigo"))
        corrective = self.client.get("/historico/", {"status": "corrective"})
        self.assertContains(corrective, "Bandeja")
        self.assertNotContains(corrective, "Troca de óleo")
        self.assertNotContains(corrective, "45.000 km")
        body = self.client.get("/historico/", {"category": "body"})
        self.assertContains(body, "Barulho na porta")
        self.assertNotContains(body, "Troca de óleo")
        period = self.client.get("/historico/", {"start": (TODAY() - timedelta(days=15)).isoformat(),
                                                 "type": "services"})
        self.assertContains(period, "Troca de óleo")
        self.assertNotContains(period, "Bandeja")
        self.assertNotContains(period, "Som antigo")
        self.assertNotContains(period, "Barulho")
        partial = self.client.get("/historico/", {"type": "problems"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(partial, "<!doctype")
        self.assertContains(self.client.get("/historico/", {"start": "2026-02-02", "end": "2026-01-01"}), "data inicial")

    def test_service_readings_are_not_duplicated(self):
        reading = OdometerReading.objects.create(vehicle=self.vehicle, date=TODAY(), kilometers=50000,
                                                 source=OdometerReading.Source.SERVICE)
        self.service(0, "10", odometer_reading=reading, kilometers=50000, title="Revisão")
        self.assertNotContains(self.client.get("/historico/", {"type": "readings"}), "50.000 km")

    def test_isolation(self):
        self.service(1, "99", vehicle=self.foreign, title="Serviço alheio")
        self.assertNotContains(self.client.get("/historico/"), "Serviço alheio")


class FinanceTests(ReportTestCase):
    def test_summary_by_period_category_and_kind(self):
        today = TODAY()
        self.service(5, "100", parts_cost=Decimal("60"), labor_cost=Decimal("40"))
        self.service(20, "300", category="suspension", kind="corrective")
        self.service(20, None, category="tires")
        old = self.service(800, "1000", category="engine", kind="corrective")
        self.service(None, "50", category="audio", kind="unspecified")
        summary = summarize(self.vehicle, [], "12m", today)
        self.assertEqual(summary["total"], Decimal("400"))
        self.assertEqual((summary["count"], summary["unpriced"]), (3, 1))
        self.assertEqual(summary["monthly_average"], Decimal("33.33"))
        self.assertEqual(summary["all_time"], Decimal("1450"))
        self.assertEqual((summary["parts"], summary["labor"]), (Decimal("60"), Decimal("40")))
        self.assertEqual([bar.key for bar in summary["by_kind"]], ["corrective", "preventive"])
        self.assertEqual(summary["by_kind"][0].percent, 100)
        self.assertEqual(len(summary["timeline"]), 12)
        self.assertEqual(sum(bar.total for bar in summary["timeline"]), Decimal("400"))
        everything = summarize(self.vehicle, [], "all", today)
        self.assertEqual(everything["total"], Decimal("1450"))
        self.assertEqual(everything["undated"], 1)
        year = summarize(self.vehicle, [], str(old.date.year), today)
        self.assertIn(Decimal("1000"), [bar.total for bar in year["by_category"]])

    def test_period_bounds(self):
        start, end = period_bounds("12m", TODAY())
        self.assertEqual(start.day, 1)
        self.assertEqual(end, TODAY())
        self.assertEqual(period_bounds("2025", TODAY())[0].isoformat(), "2025-01-01")
        self.assertEqual(period_bounds("all", TODAY()), (None, None))

    def test_forecast_uses_dates_and_average_km(self):
        today = TODAY()
        OdometerReading.objects.create(vehicle=self.vehicle, date=today - timedelta(days=100), kilometers=40000)
        OdometerReading.objects.create(vehicle=self.vehicle, date=today, kilometers=45000)
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Por data", next_date=today + timedelta(days=60),
                                       estimated_cost=Decimal("200"))
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Por km", next_km=50000, estimated_cost=Decimal("300"))
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Longe", next_km=90000, estimated_cost=Decimal("999"))
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Sem ref")
        response = self.client.get("/financas/")
        forecast = response.context["summary"]["forecast"]
        self.assertEqual([plan.title for _, plan in forecast["items"]], ["Por data", "Por km"])
        self.assertEqual(forecast["items"][1][0], today + timedelta(days=100))
        self.assertEqual(forecast["total"], Decimal("500"))
        self.assertEqual(forecast["without_date"], 1)
        self.assertContains(response, "50,0 km por dia")

    def test_page_periods_and_isolation(self):
        self.service(3, "123.45", title="Meu")
        self.service(3, "999", vehicle=self.foreign)
        response = self.client.get("/financas/")
        self.assertContains(response, "R$ 123,45")
        self.assertNotContains(response, "R$ 999,00")
        self.assertEqual(self.client.get("/financas/", {"periodo": "invalido"}).context["period"], "12m")
        self.assertEqual(self.client.get("/financas/", {"periodo": "all"}).status_code, 200)


class CsvTests(ReportTestCase):
    def test_cell_formatting_and_formula_injection(self):
        self.assertEqual(cell(Decimal("1234.5")), "1234,50")
        self.assertEqual(cell(TODAY().replace(year=2026, month=1, day=2)), "02/01/2026")
        self.assertEqual(cell(True), "Sim")
        for dangerous in ("=HYPERLINK(\"x\")", "+1", "-2", "@cmd", "\tx"):
            self.assertTrue(cell(dangerous).startswith("'"))
        self.assertEqual(cell("Normal"), "Normal")

    def test_exports(self):
        service = self.service(1, "89.9", workshop="=cmd|'/c calc'!A1", title="Óleo")
        ServicePart.objects.create(service=service, name="Filtro", brand_model="Tecfil")
        self.service(1, "10", vehicle=self.foreign, title="Alheio")
        response = self.client.get("/dados/csv/servicos/")
        self.assertIn("attachment", response["Content-Disposition"])
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("\ufeffVeículo;Data;Km"))
        self.assertIn("89,90", text)
        self.assertIn("'=cmd", text)
        self.assertIn("Filtro (Tecfil)", text)
        self.assertNotIn("Alheio", text)
        for kind in ("problemas", "quilometragem", "plano"):
            self.assertEqual(self.client.get(f"/dados/csv/{kind}/").status_code, 200)
        self.assertEqual(self.client.get("/dados/csv/usuarios/").status_code, 404)
        self.assertIn("no-store", response["Cache-Control"])

    def test_render_csv_escapes_separator(self):
        self.service(1, "1", title="Óleo; filtro")
        self.assertIn('"Óleo; filtro"', render_csv(services(self.owner)))


class BackupTests(ReportTestCase):
    def populate(self):
        reading = OdometerReading.objects.create(vehicle=self.vehicle, date=TODAY() - timedelta(days=30), kilometers=40000)
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Óleo", interval_km=10000, source="Manual",
                                              source_verified=True, kind="manufacturer", suggestion_key="oil",
                                              estimated_cost=Decimal("250"))
        service_reading = OdometerReading.objects.create(vehicle=self.vehicle, date=TODAY() - timedelta(days=10),
                                                         kilometers=41000, source="service")
        service = ServiceRecord.objects.create(vehicle=self.vehicle, category="oil", title="Troca", plan=plan,
                                               date=service_reading.date, kilometers=41000, total_cost=Decimal("180.50"),
                                               odometer_reading=service_reading)
        ServicePart.objects.create(service=service, name="Filtro", brand_model="Tecfil")
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Água na porta",
                                         status="resolved", ruled_out="Não é combustível", resolved_by_service=service)
        ProblemUpdate.objects.create(problem=problem, date=TODAY(), status="resolved", note="Drenado")
        attachment = Attachment(service=service, original_name="nota.png", content_type="image/png", size=len(PNG))
        attachment.file.save("x.png", ContentFile(PNG), save=True)
        prefs = AlertPreferences.for_user(self.owner)
        prefs.km_ahead = 700
        prefs.save()
        UsageProfile.objects.create(vehicle=self.vehicle, parked_days=True, frequent_load=True)
        return reading

    def backup_upload(self, user=None):
        handle, size, missing = create_backup(user or self.owner)
        self.assertEqual(missing, 0)
        return SimpleUploadedFile("backup.zip", handle.read(), content_type="application/zip")

    def test_round_trip_restores_everything(self):
        self.populate()
        upload = self.backup_upload()
        restored_user = get_user_model().objects.create_user(username="restored")
        counts = restore_backup(restored_user, upload)
        self.assertEqual(counts, {"vehicles": 1, "readings": 2, "plans": 1, "services": 1, "parts": 1, "problems": 1,
                                  "problem_updates": 1, "usage_profiles": 1, "attachments": 1})
        vehicle = Vehicle.objects.get(owner=restored_user)
        self.assertEqual(vehicle.usage_profile.active_flags, ["parked_days", "frequent_load"])
        service = vehicle.services.get()
        self.assertEqual((service.title, service.total_cost, service.kilometers), ("Troca", Decimal("180.50"), 41000))
        self.assertEqual(service.plan.title, "Óleo")
        self.assertEqual(service.plan.vehicle, vehicle)
        self.assertEqual(service.odometer_reading.kilometers, 41000)
        self.assertEqual(service.parts.get().brand_model, "Tecfil")
        problem = vehicle.problems.get()
        self.assertEqual((problem.resolved_by_service, problem.ruled_out), (service, "Não é combustível"))
        self.assertEqual(problem.updates.get().note, "Drenado")
        attachment = service.attachments.get()
        with attachment.file.open("rb") as restored:
            self.assertEqual(restored.read(), PNG)
        self.assertEqual(vehicle.latest_reading.kilometers, 41000)
        self.assertEqual(AlertPreferences.for_user(restored_user).km_ahead, 700)
        self.assertTrue(vehicle.plans.get().source_verified)
        self.assertEqual(Vehicle.objects.filter(owner=self.owner).count(), 1)

    def test_backup_excludes_other_users(self):
        self.service(1, "10", vehicle=self.foreign, title="Alheio")
        handle, _, _ = create_backup(self.owner)
        with zipfile.ZipFile(handle) as archive:
            data = json.loads(archive.read("data.json"))
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["format"], "rodagem-backup")
        self.assertEqual([vehicle["brand"] for vehicle in data["vehicles"]], ["Exemplo"])
        self.assertFalse(data["services"])
        self.assertNotIn("owner", data["vehicles"][0])

    def test_restore_refused_when_account_has_vehicles(self):
        with self.assertRaisesMessage(BackupError, "conta sem veículos"):
            restore_backup(self.owner, self.backup_upload())

    def build_zip(self, members):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return SimpleUploadedFile("backup.zip", buffer.getvalue())

    def test_rejects_invalid_archives(self):
        empty_user = get_user_model().objects.create_user(username="empty")
        manifest = json.dumps({"format": "rodagem-backup", "version": 1})
        cases = {
            "não é um backup válido": SimpleUploadedFile("x.zip", b"not a zip"),
            "itens inesperados": self.build_zip({"manifest.json": manifest, "data.json": "{}", "../evil.txt": "x"}),
            "Versão de backup": self.build_zip({"manifest.json": json.dumps({"format": "rodagem-backup", "version": 99}),
                                                 "data.json": "{}"}),
            "não é um backup do Rodagem": self.build_zip({"manifest.json": "{}", "data.json": "{}"}),
            "corrompido": self.build_zip({"manifest.json": manifest, "data.json": "{broken"}),
        }
        for message, upload in cases.items():
            with self.subTest(message=message), self.assertRaisesMessage(BackupError, message):
                restore_backup(empty_user, upload)

    def test_tampered_attachment_rolls_back_everything(self):
        self.populate()
        handle, _, _ = create_backup(self.owner)
        with zipfile.ZipFile(handle) as source:
            members = {info.filename: source.read(info) for info in source.infolist()}
        attachment_name = next(name for name in members if name.startswith("attachments/"))
        members[attachment_name] = PNG + b"tampered"
        empty_user = get_user_model().objects.create_user(username="empty")
        files_before = sorted(Path(self.media_root).rglob("*"))
        with self.assertRaisesMessage(BackupError, "corrompido"):
            restore_backup(empty_user, self.build_zip(members))
        self.assertFalse(Vehicle.objects.filter(owner=empty_user).exists())
        self.assertEqual(sorted(Path(self.media_root).rglob("*")), files_before)

    def test_invalid_reference_rolls_back(self):
        empty_user = get_user_model().objects.create_user(username="empty")
        data = {"vehicles": [{"id": 1, "brand": "A", "model": "B", "version": "", "manufacture_year": None,
                              "model_year": 2020, "engine": "", "engine_verified": False, "fuel": "flex",
                              "acquisition_date": None, "plate": "", "notes": ""}],
                "readings": [{"id": 1, "vehicle_id": 999, "date": "2025-01-01", "kilometers": 10, "source": "panel", "notes": ""}]}
        upload = self.build_zip({"manifest.json": json.dumps({"format": "rodagem-backup", "version": 1}),
                                 "data.json": json.dumps(data)})
        with self.assertRaisesMessage(BackupError, "Nada foi importado"):
            restore_backup(empty_user, upload)
        self.assertFalse(Vehicle.objects.filter(owner=empty_user).exists())

    def test_web_download_restore_and_backup_alert(self):
        self.populate()
        self.assertContains(self.client.get("/"), "Faça um backup dos seus dados")
        self.assertEqual(self.client.get("/dados/backup/").status_code, 405)
        response = self.client.post("/dados/backup/")
        self.assertEqual(response["Content-Type"], "application/zip")
        content = b"".join(response.streaming_content)
        self.assertTrue(BackupRecord.objects.filter(owner=self.owner, source="web").exists())
        self.assertNotContains(self.client.get("/"), "Faça um backup dos seus dados")
        self.assertContains(self.client.get("/dados/"), "Disponível apenas em uma conta sem veículos")
        new_user = get_user_model().objects.create_user(username="new")
        self.client.force_login(new_user)
        self.assertContains(self.client.get("/dados/"), "Restaurar")
        missing_confirm = self.client.post("/dados/restaurar/", {"backup": SimpleUploadedFile("b.zip", content)}, follow=True)
        self.assertContains(missing_confirm, "obrigatório")
        restored = self.client.post("/dados/restaurar/", {"backup": SimpleUploadedFile("b.zip", content), "confirm": "on"},
                                    follow=True)
        self.assertContains(restored, "Backup restaurado: 1 veículo(s)")
        self.assertContains(restored, "Exemplo Compacto 2022")

    def test_command_writes_backup(self):
        self.populate()
        output = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)
        call_command("export_backup", username="owner", output=output, stdout=io.StringIO())
        files = list(Path(output).glob("rodagem-backup-owner-*.zip"))
        self.assertEqual(len(files), 1)
        self.assertTrue(zipfile.is_zipfile(files[0]))
        self.assertTrue(BackupRecord.objects.filter(owner=self.owner, source="command").exists())


class PageTests(ReportTestCase):
    def test_pages_render_and_require_login(self):
        for path in ("/historico/", "/financas/", "/dados/", "/mais/", "/financas/?periodo=all"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.client.logout()
        for path in ("/historico/", "/financas/", "/dados/", "/mais/", "/dados/csv/servicos/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)
        self.assertEqual(self.client.post("/dados/backup/").status_code, 302)
