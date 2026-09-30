import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from garage.models import OdometerReading, Vehicle
from garage.services import record_reading

from .attachments import MAX_FILE_SIZE
from .forms import MoneyField, normalize_money
from .models import Attachment, Problem, ProblemUpdate, ServicePart, ServiceRecord

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64
TODAY = timezone.localdate


def parts_data(*rows, initial=0):
    data = {"parts-TOTAL_FORMS": str(max(len(rows), 1)), "parts-INITIAL_FORMS": str(initial),
            "parts-MIN_NUM_FORMS": "0", "parts-MAX_NUM_FORMS": "30"}
    for index, row in enumerate(rows or [{}]):
        for key, value in row.items():
            data[f"parts-{index}-{key}"] = value
    return data


class MediaTestCase(TestCase):
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
        cls.vehicle = Vehicle.objects.create(owner=cls.owner, brand="Exemplo", model="Compacto", model_year=2020)
        cls.second = Vehicle.objects.create(owner=cls.owner, brand="Toyota", model="Etios", model_year=2018)
        cls.foreign = Vehicle.objects.create(owner=cls.other, brand="Other", model="Private", model_year=2020)

    def setUp(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_vehicle_id"] = self.vehicle.pk
        session.save()

    def post_service(self, url="/servicos/novo/", parts=(), **fields):
        data = {"category": "oil", "kind": "unspecified", **fields, **parts_data(*parts)}
        return self.client.post(url, data)

    def reading(self, days, kilometers, vehicle=None):
        return record_reading(owner=self.owner, vehicle_id=(vehicle or self.vehicle).pk,
                              date=TODAY() - timedelta(days=days), kilometers=kilometers,
                              source=OdometerReading.Source.PANEL)


class MoneyTests(TestCase):
    def test_brazilian_formats(self):
        cases = {"89,90": "89.90", "R$ 1.234,56": "1234.56", "1.500": "1500", "150.5": "150.5", "1500": "1500"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_money(raw), expected)

    def test_field_rejects_invalid_and_negative(self):
        field = MoneyField()
        self.assertEqual(field.clean("1.234,56"), Decimal("1234.56"))
        self.assertIsNone(field.clean(""))
        for raw in ("-5", "abc", "1,2,3"):
            with self.subTest(raw=raw), self.assertRaises(Exception):
                field.clean(raw)
        self.assertEqual(field.prepare_value(Decimal("89.9")), "89,90")


class ServiceTests(MediaTestCase):
    def test_only_category_is_required(self):
        response = self.post_service(date="")
        service = ServiceRecord.objects.get()
        self.assertRedirects(response, f"/servicos/{service.pk}/")
        self.assertIsNone(service.date)
        self.assertEqual(service.display_title, "Óleo e filtro de óleo")
        self.assertEqual(service.vehicle, self.vehicle)
        self.assertFalse(OdometerReading.objects.exists())
        self.assertEqual(self.post_service(category="").status_code, 200)

    def test_service_mileage_updates_history_and_follows_edits(self):
        self.reading(30, 40000)
        response = self.post_service(date=TODAY().isoformat(), kilometers=41000, title="Troca de óleo")
        service = ServiceRecord.objects.get()
        self.assertEqual(service.odometer_reading.source, OdometerReading.Source.SERVICE)
        self.assertEqual(self.vehicle.latest_reading.kilometers, 41000)
        self.assertContains(self.client.get(response.url), "Quilometragem atual atualizada para 41.000 km")
        self.post_service(f"/servicos/{service.pk}/editar/", date=TODAY().isoformat(), kilometers=41500)
        service.refresh_from_db()
        self.assertEqual(service.odometer_reading.kilometers, 41500)
        self.assertEqual(self.vehicle.readings.count(), 2)
        self.post_service(f"/servicos/{service.pk}/editar/", date=TODAY().isoformat(), kilometers="")
        service.refresh_from_db()
        self.assertIsNone(service.odometer_reading)
        self.assertEqual(self.vehicle.readings.count(), 1)

    def test_inconsistent_mileage_is_rejected(self):
        self.reading(0, 45000)
        response = self.post_service(date=(TODAY() - timedelta(days=10)).isoformat(), kilometers=46000)
        self.assertContains(response, "maior que a leitura de 45.000 km")
        self.assertFalse(ServiceRecord.objects.exists())

    def test_same_day_reading_is_kept(self):
        existing = self.reading(0, 45000)
        self.post_service(date=TODAY().isoformat(), kilometers=45010)
        service = ServiceRecord.objects.get()
        self.assertIsNone(service.odometer_reading)
        self.assertEqual(list(self.vehicle.readings.all()), [existing])

    def test_costs(self):
        self.post_service(parts_cost="120,50", labor_cost="80")
        self.assertEqual(ServiceRecord.objects.get().total_cost, Decimal("200.50"))
        response = self.post_service(parts_cost="300", labor_cost="80", total_cost="100")
        self.assertContains(response, "somam mais que o valor total")
        self.post_service(total_cost="R$ 1.234,56", category="tires")
        self.assertEqual(ServiceRecord.objects.get(category="tires").total_cost, Decimal("1234.56"))

    def test_dates_are_validated(self):
        tomorrow = (TODAY() + timedelta(days=1)).isoformat()
        self.assertContains(self.post_service(date=tomorrow), "não pode estar no futuro")
        response = self.post_service(date=TODAY().isoformat(), warranty_until=(TODAY() - timedelta(days=1)).isoformat())
        self.assertContains(response, "garantia não pode terminar antes")

    def test_parts_add_and_remove(self):
        self.post_service(parts=[{"name": "Filtro de óleo", "brand_model": "Tecfil PSL"}, {"name": "Óleo 5W30"}])
        service = ServiceRecord.objects.get()
        self.assertEqual(service.parts.count(), 2)
        first, second = service.parts.all()
        data = {"category": "oil", "kind": "unspecified",
                **parts_data({"id": first.pk, "name": first.name, "DELETE": "on"}, {"id": second.pk, "name": second.name}, initial=2)}
        self.client.post(f"/servicos/{service.pk}/editar/", data)
        self.assertEqual(list(service.parts.values_list("name", flat=True)), ["Óleo 5W30"])
        self.assertContains(self.client.get("/servicos/", {"q": "5W30"}), "Óleo e filtro de óleo")

    def test_delete_removes_generated_reading_and_files(self):
        self.client.post("/servicos/novo/", {"category": "oil", "kind": "unspecified", "date": TODAY().isoformat(),
                         "kilometers": 1000, "attachments": [SimpleUploadedFile("nota.pdf", PDF)], **parts_data()})
        service = ServiceRecord.objects.get()
        path = Path(service.attachments.get().file.path)
        self.assertTrue(path.exists())
        self.assertEqual(self.client.get(f"/servicos/{service.pk}/excluir/").status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/servicos/{service.pk}/excluir/")
        self.assertRedirects(response, "/servicos/")
        self.assertFalse(ServiceRecord.objects.exists())
        self.assertFalse(OdometerReading.objects.exists())
        self.assertFalse(Attachment.objects.exists())
        self.assertFalse(path.exists())

    def test_service_resolves_problem(self):
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Barulho", reported_on=TODAY())
        form_page = self.client.get(f"/servicos/novo/?problema={problem.pk}")
        self.assertContains(form_page, "linked-problem")
        self.client.post(f"/servicos/novo/?problema={problem.pk}", {
            "category": "suspension", "kind": "corrective", "date": TODAY().isoformat(), "resolves": problem.pk, **parts_data()})
        problem.refresh_from_db()
        service = ServiceRecord.objects.get()
        self.assertEqual(problem.status, Problem.Status.RESOLVED)
        self.assertEqual(problem.resolved_by_service, service)
        self.assertEqual(problem.resolved_on, TODAY())
        self.assertTrue(problem.updates.filter(status=Problem.Status.RESOLVED).exists())

    def test_service_from_problem_uses_problem_vehicle(self):
        problem = Problem.objects.create(vehicle=self.second, symptom="noise", description="Barulho")
        self.client.post(f"/servicos/novo/?problema={problem.pk}", {
            "category": "brakes", "kind": "unspecified", "resolves": problem.pk, **parts_data()})
        self.assertEqual(ServiceRecord.objects.get().vehicle, self.second)

    def test_resolves_rejects_service_before_report(self):
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Barulho", reported_on=TODAY())
        response = self.post_service(date=(TODAY() - timedelta(days=5)).isoformat(), resolves=problem.pk)
        self.assertContains(response, "anterior ao relato")

    def test_list_filters_totals_and_partial(self):
        self.post_service(total_cost="100", title="Troca de óleo")
        self.post_service(category="tires", total_cost="50,25", title="Rodízio")
        self.post_service(category="tires")
        response = self.client.get("/servicos/")
        self.assertContains(response, "R$ 150,25")
        self.assertContains(response, "1 sem valor")
        filtered = self.client.get("/servicos/", {"category": "oil"})
        self.assertContains(filtered, "Troca de óleo")
        self.assertNotContains(filtered, "Rodízio")
        partial = self.client.get("/servicos/", {"q": "óleo"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(partial, "<!doctype")
        self.assertContains(self.client.get("/servicos/", {"start": "2025-01-02", "end": "2025-01-01"}), "data inicial")

    def test_list_shows_active_vehicle_only_and_switch(self):
        ServiceRecord.objects.create(vehicle=self.second, category="battery", title="Bateria do Etios")
        self.assertNotContains(self.client.get("/servicos/"), "Bateria do Etios")
        response = self.client.post("/veiculos/trocar/", {"vehicle": self.second.pk, "next": "/servicos/"})
        self.assertRedirects(response, "/servicos/")
        self.assertContains(self.client.get("/servicos/"), "Bateria do Etios")
        self.assertEqual(self.client.post("/veiculos/trocar/", {"vehicle": self.foreign.pk}).status_code, 404)
        unsafe = self.client.post("/veiculos/trocar/", {"vehicle": self.vehicle.pk, "next": "https://example.com/"})
        self.assertRedirects(unsafe, "/")


class ProblemTests(MediaTestCase):
    def create_problem(self, **fields):
        data = {"symptom": "noise", "description": "Barulho ao frear", "severity": "unknown", "status": "open", **fields}
        return self.client.post("/problemas/novo/", data)

    def test_minimal_problem(self):
        response = self.create_problem(reported_on="")
        problem = Problem.objects.get()
        self.assertRedirects(response, f"/problemas/{problem.pk}/")
        self.assertEqual(problem.status, Problem.Status.OPEN)
        self.assertIsNone(problem.reported_on)
        self.assertEqual(problem.display_title, "Barulho ao frear")
        self.assertEqual(self.create_problem(description="").status_code, 200)

    def test_resolved_history_without_dates(self):
        self.client.post("/problemas/novo/", {
            "symptom": "noise", "title": "Rangido no painel", "description": "Rangido no painel em piso irregular.",
            "location": "Painel", "category": "body", "status": "resolved", "severity": "unknown",
            "diagnosis": "Presilha solta.", "solution": "Presilha substituída.", "ruled_out": "Não era a suspensão.",
        })
        problem = Problem.objects.get()
        self.assertEqual(problem.status, Problem.Status.RESOLVED)
        self.assertIsNone(problem.reported_on)
        self.assertIsNone(problem.resolved_on)
        detail = self.client.get(f"/problemas/{problem.pk}/")
        self.assertContains(detail, "Causas já descartadas")
        self.assertContains(detail, "Data desconhecida")
        self.assertContains(self.client.get("/problemas/", {"view": "closed"}), "Rangido no painel")
        self.assertNotContains(self.client.get("/problemas/"), "Rangido no painel")

    def test_follow_up_until_resolution_and_reopening(self):
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Barulho",
                                         reported_on=TODAY() - timedelta(days=10))
        url = f"/problemas/{problem.pk}/"
        self.assertContains(self.client.post(url, {"date": TODAY().isoformat(), "status": "", "note": ""}), "Escreva o que aconteceu")
        early = (TODAY() - timedelta(days=11)).isoformat()
        self.assertContains(self.client.post(url, {"date": early, "status": "", "note": "x"}), "anterior ao relato")
        self.client.post(url, {"date": TODAY().isoformat(), "status": "", "note": "Voltou a acontecer"})
        self.client.post(url, {"date": TODAY().isoformat(), "status": "resolved", "note": "Oficina apertou a bandeja."})
        problem.refresh_from_db()
        self.assertEqual(problem.status, Problem.Status.RESOLVED)
        self.assertEqual(problem.resolved_on, TODAY())
        self.assertEqual(problem.solution, "Oficina apertou a bandeja.")
        self.client.post(url, {"date": TODAY().isoformat(), "status": "open", "note": "Voltou."})
        problem.refresh_from_db()
        self.assertIsNone(problem.resolved_on)
        self.assertEqual(problem.updates.count(), 3)
        self.assertContains(self.client.get(url), "Voltou a acontecer")

    def test_edit_status_change_is_logged(self):
        self.create_problem()
        problem = Problem.objects.get()
        self.client.post(f"/problemas/{problem.pk}/editar/", {
            "symptom": "noise", "description": "Barulho", "severity": "low", "status": "monitoring"})
        self.assertEqual(ProblemUpdate.objects.get().status, Problem.Status.MONITORING)

    def test_high_severity_notice_and_delete(self):
        self.create_problem(severity="high")
        problem = Problem.objects.get()
        self.assertContains(self.client.get(f"/problemas/{problem.pk}/"), "procure avaliação profissional")
        self.assertContains(self.client.get("/"), "Gravidade alta")
        self.client.post(f"/problemas/{problem.pk}/excluir/")
        self.assertFalse(Problem.objects.exists())

    def test_service_link_must_belong_to_vehicle(self):
        foreign_service = ServiceRecord.objects.create(vehicle=self.second, category="oil")
        response = self.create_problem(resolved_by_service=foreign_service.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Problem.objects.exists())


class AttachmentTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.service = ServiceRecord.objects.create(vehicle=self.vehicle, category="oil")
        self.problem = Problem.objects.create(vehicle=self.vehicle, symptom="leak", description="Mancha no chão")

    def upload(self, url, *files):
        return self.client.post(url, {"attachments": list(files)}, follow=True)

    def test_upload_download_and_delete(self):
        self.upload(f"/servicos/{self.service.pk}/anexos/", SimpleUploadedFile("../foto nota.png", PNG),
                    SimpleUploadedFile("nota.pdf", PDF))
        image, pdf = self.service.attachments.all()
        self.assertEqual(image.original_name, "foto_nota.png")
        self.assertRegex(image.file.name, r"^attachments/[0-9a-f]{32}\.png$")
        response = self.client.get(f"/anexos/{image.pk}/")
        response.close()
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertIn("no-store", response["Cache-Control"])
        pdf_response = self.client.get(f"/anexos/{pdf.pk}/")
        pdf_response.close()
        self.assertIn("attachment", pdf_response["Content-Disposition"])
        path = Path(image.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/anexos/{image.pk}/excluir/")
        self.assertFalse(path.exists())
        self.assertEqual(self.service.attachments.count(), 1)

    def test_rejects_disguised_and_large_files(self):
        response = self.upload(f"/problemas/{self.problem.pk}/anexos/", SimpleUploadedFile("foto.jpg", b"<script>x</script>"))
        self.assertContains(response, "formato não aceito")
        big = SimpleUploadedFile("grande.png", PNG + b"0" * MAX_FILE_SIZE)
        self.assertContains(self.upload(f"/problemas/{self.problem.pk}/anexos/", big), "maior que 10 MB")
        self.assertFalse(Attachment.objects.exists())

    def test_problem_create_with_photo(self):
        self.client.post("/problemas/novo/", {"symptom": "leak", "description": "Gotas", "severity": "low", "status": "open",
                                              "attachments": [SimpleUploadedFile("vazamento.png", PNG)]})
        self.assertEqual(Problem.objects.get(description="Gotas").attachments.count(), 1)


class IsolationTests(MediaTestCase):
    def test_other_owner_records_are_not_reachable(self):
        service = ServiceRecord.objects.create(vehicle=self.foreign, category="oil", title="Serviço alheio")
        problem = Problem.objects.create(vehicle=self.foreign, symptom="noise", description="Problema alheio")
        attachment = Attachment.objects.create(service=service, file="attachments/x.png", original_name="x.png",
                                               content_type="image/png", size=1)
        for path in [f"/servicos/{service.pk}/", f"/servicos/{service.pk}/editar/", f"/servicos/{service.pk}/excluir/",
                     f"/servicos/{service.pk}/anexos/", f"/problemas/{problem.pk}/", f"/problemas/{problem.pk}/editar/",
                     f"/problemas/{problem.pk}/excluir/", f"/problemas/{problem.pk}/anexos/", f"/anexos/{attachment.pk}/",
                     f"/anexos/{attachment.pk}/excluir/", f"/servicos/novo/?problema={problem.pk}"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, {}).status_code, 404)
        self.assertTrue(ServiceRecord.objects.filter(pk=service.pk).exists())
        self.assertNotContains(self.client.get("/servicos/"), "Serviço alheio")
        self.assertNotContains(self.client.get("/problemas/", {"view": "all"}), "Problema alheio")

    def test_cannot_resolve_problem_from_another_vehicle(self):
        Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Problema deste carro")
        other_problem = Problem.objects.create(vehicle=self.second, symptom="noise", description="x")
        response = self.post_service(resolves=other_problem.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceRecord.objects.exists())
        other_problem.refresh_from_db()
        self.assertTrue(other_problem.is_active)

    def test_login_required(self):
        self.client.logout()
        for path in ["/registrar/", "/servicos/", "/servicos/novo/", "/problemas/", "/problemas/novo/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)

    def test_pages_render(self):
        service = ServiceRecord.objects.create(vehicle=self.vehicle, category="oil", total_cost=Decimal("10"))
        ServicePart.objects.create(service=service, name="Filtro")
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="x")
        for path in ["/", "/registrar/", "/servicos/", "/servicos/novo/", f"/servicos/{service.pk}/",
                     f"/servicos/{service.pk}/editar/", f"/servicos/{service.pk}/excluir/", "/problemas/",
                     "/problemas/novo/", f"/problemas/{problem.pk}/", f"/problemas/{problem.pk}/editar/",
                     f"/problemas/{problem.pk}/excluir/", f"/servicos/novo/?problema={problem.pk}"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_no_vehicle_redirects_to_creation(self):
        self.client.force_login(self.other)
        Vehicle.objects.filter(owner=self.other).delete()
        self.assertRedirects(self.client.get("/servicos/novo/"), "/veiculos/novo/")
        self.assertContains(self.client.get("/registrar/"), "Cadastre um veículo")
