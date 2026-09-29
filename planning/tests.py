from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from garage.models import OdometerReading, Vehicle
from maintenance.models import Problem, ProblemUpdate, ServiceRecord

from .alerts import build_alerts, evaluate_plans
from .catalog import SUGGESTIONS
from .models import AlertPreferences, MaintenancePlan
from .rules import add_months, evaluate

TODAY = timezone.localdate
Status = MaintenancePlan.Status


def parts_data():
    return {"parts-TOTAL_FORMS": "1", "parts-INITIAL_FORMS": "0", "parts-MIN_NUM_FORMS": "0", "parts-MAX_NUM_FORMS": "30"}


class RuleTests(SimpleTestCase):
    def plan(self, **fields):
        values = {"status": Status.PENDING, "interval_km": None, "interval_months": None, "next_km": None,
                  "next_date": None, "scheduled_for": None, "Status": Status}
        return SimpleNamespace(**{**values, **fields})

    def service(self, day=None, km=None, pk=1):
        return SimpleNamespace(date=day, kilometers=km, pk=pk)

    def run_rule(self, plan, services=(), km=None, today=date(2026, 9, 29)):
        reading = SimpleNamespace(kilometers=km) if km is not None else None
        return evaluate(plan, list(services), reading, today, 1000, 30)

    def test_add_months_clamps_day(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2027, 11, 15), 3), date(2028, 2, 15))
        self.assertEqual(add_months(date(2028, 1, 31), 1), date(2028, 2, 29))

    def test_recurring_uses_last_service_and_whichever_comes_first(self):
        plan = self.plan(interval_km=10000, interval_months=12)
        due = self.run_rule(plan, [self.service(date(2026, 1, 10), 40000)], km=45000)
        self.assertEqual((due.next_km, due.next_date), (50000, date(2027, 1, 10)))
        self.assertEqual(due.state, "ok")
        self.assertEqual(self.run_rule(plan, [self.service(date(2026, 1, 10), 40000)], km=49500).state, "soon")
        self.assertEqual(self.run_rule(plan, [self.service(date(2026, 1, 10), 40000)], km=50001).state, "overdue")
        by_time = self.run_rule(plan, [self.service(date(2025, 9, 1), 40000)], km=41000)
        self.assertEqual(by_time.state, "overdue")
        self.assertIn("passou 28 dias", by_time.summary)

    def test_latest_service_wins(self):
        plan = self.plan(interval_km=10000)
        services = [self.service(date(2025, 1, 1), 30000, 1), self.service(date(2026, 1, 1), 40000, 2)]
        self.assertEqual(self.run_rule(plan, services, km=41000).next_km, 50000)

    def test_unknown_and_needs_km(self):
        self.assertEqual(self.run_rule(self.plan(interval_km=10000)).state, "unknown")
        self.assertEqual(self.run_rule(self.plan(interval_km=10000), [self.service()]).summary,
                         "Realização registrada sem data ou km")
        self.assertEqual(self.run_rule(self.plan(next_km=50000)).state, "needs_km")

    def test_manual_target_and_scheduled(self):
        plan = self.plan(next_date=date(2026, 10, 10))
        self.assertEqual(self.run_rule(plan).state, "soon")
        scheduled = self.plan(next_date=date(2026, 10, 10), status=Status.SCHEDULED, scheduled_for=date(2026, 10, 5))
        self.assertEqual(self.run_rule(scheduled).state, "scheduled")
        overdue_scheduled = self.plan(next_date=date(2026, 9, 1), status=Status.SCHEDULED, scheduled_for=date(2026, 10, 5))
        self.assertEqual(self.run_rule(overdue_scheduled).state, "overdue")

    def test_closed_states(self):
        self.assertEqual(self.run_rule(self.plan(status=Status.DONE)).state, "done")
        self.assertEqual(self.run_rule(self.plan(status=Status.DISMISSED, interval_km=5)).state, "dismissed")


class PlanTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="owner")
        cls.other = user_model.objects.create_user(username="other")
        cls.vehicle = Vehicle.objects.create(owner=cls.owner, brand="Exemplo", model="Compacto", model_year=2022)
        cls.second = Vehicle.objects.create(owner=cls.owner, brand="Toyota", model="Etios", model_year=2018)
        cls.foreign = Vehicle.objects.create(owner=cls.other, brand="Other", model="Private", model_year=2020)

    def setUp(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_vehicle_id"] = self.vehicle.pk
        session.save()

    def reading(self, days_ago, km):
        return OdometerReading.objects.create(vehicle=self.vehicle, date=TODAY() - timedelta(days=days_ago), kilometers=km)

    def alerts(self, prefs=None):
        prefs = prefs or AlertPreferences.for_user(self.owner)
        return build_alerts(self.vehicle, prefs, evaluate_plans(self.vehicle, prefs, TODAY()), TODAY())


class AlertTests(PlanTestCase):
    def test_overdue_and_soon_explain_reason_without_alarm(self):
        self.reading(1, 51000)
        oil = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Óleo", interval_km=10000, priority="high",
                                             kind="manufacturer")
        ServiceRecord.objects.create(vehicle=self.vehicle, category="oil", date=TODAY() - timedelta(days=100),
                                     kilometers=40000, plan=oil)
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Bateria", next_date=TODAY() + timedelta(days=10))
        alerts = self.alerts()
        self.assertEqual(alerts[0].title, "Óleo: passou da referência")
        self.assertTrue(alerts[0].urgent)
        self.assertIn("passou 1.000 km", alerts[0].message)
        self.assertIn("não foi conferido no manual", alerts[0].message)
        self.assertTrue(any(alert.title == "Bateria: está chegando" for alert in alerts))
        for alert in alerts:
            self.assertNotIn("defeito", alert.message.lower())

    def test_unknown_items_are_grouped_and_priorities_filtered(self):
        for title in ("A", "B", "C", "D"):
            MaintenancePlan.objects.create(vehicle=self.vehicle, title=title)
        grouped = [alert for alert in self.alerts() if "sem referência" in alert.title]
        self.assertEqual(len(grouped), 1)
        self.assertIn("4 itens", grouped[0].title)
        self.assertIn("e mais 1", grouped[0].message)
        prefs = AlertPreferences.for_user(self.owner)
        prefs.show_low = False
        prefs.save()
        self.assertFalse([alert for alert in self.alerts(prefs) if alert.level == "low"])

    def test_odometer_alerts(self):
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Óleo", interval_km=10000)
        self.assertTrue(any(alert.title == "Informe a quilometragem atual" for alert in self.alerts()))
        self.reading(45, 40000)
        self.assertTrue(any("Última leitura de km há 45 dias" in alert.title for alert in self.alerts()))

    def test_problem_warranty_and_recurrence_alerts(self):
        Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Barulho", severity="high",
                               reported_on=TODAY() - timedelta(days=40), location="Porta traseira")
        resolved = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="Antes", status="resolved",
                                          reported_on=TODAY() - timedelta(days=200), location="porta traseira ")
        ProblemUpdate.objects.create(problem=resolved, date=TODAY() - timedelta(days=150), status="resolved")
        ServiceRecord.objects.create(vehicle=self.vehicle, category="brakes", title="Pastilhas",
                                     date=TODAY() - timedelta(days=80), warranty_until=TODAY() + timedelta(days=5))
        titles = [alert.title for alert in self.alerts()]
        self.assertIn("Problema em aberto: Barulho", titles)
        self.assertIn("Sem acompanhamento há 40 dias: Barulho", titles)
        self.assertIn("Sintoma recorrente: Ruído · Porta traseira", titles)
        self.assertIn("Garantia termina em 5 dias: Pastilhas", titles)
        high = next(alert for alert in self.alerts() if alert.title.startswith("Problema em aberto"))
        self.assertIn("não é um diagnóstico", high.message)

    def test_diagnosis_items_and_past_schedule(self):
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Ruído na suspensão", kind="diagnosis",
                                       reason="Oficina sugeriu avaliar.")
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Alinhamento", status="scheduled",
                                       scheduled_for=TODAY() - timedelta(days=2))
        titles = [alert.title for alert in self.alerts()]
        self.assertIn("Ruído na suspensão: avaliação profissional", titles)
        self.assertTrue(any(title.startswith("Alinhamento: programado para") for title in titles))

    def test_dismissed_and_other_vehicle_do_not_alert(self):
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="X", next_date=TODAY() - timedelta(days=1),
                                       status="dismissed", dismissed_reason="Não se aplica")
        MaintenancePlan.objects.create(vehicle=self.second, title="Y", next_date=TODAY() - timedelta(days=1))
        self.assertFalse(self.alerts())


class CompletionTests(PlanTestCase):
    def create_service(self, target, **fields):
        data = {"category": "oil", "kind": "preventive", "date": TODAY().isoformat(), **parts_data(), **fields}
        return self.client.post(f"/servicos/novo/?plano={target.pk}", data)

    def test_recurring_plan_recalculates_after_service(self):
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Óleo", interval_km=10000, interval_months=12,
                                              next_km=1, status="scheduled", scheduled_for=TODAY())
        form = self.client.get(f"/servicos/novo/?plano={plan.pk}")
        self.assertContains(form, 'value="Óleo"')
        self.create_service(plan, plan=plan.pk, kilometers=45000)
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.next_km, plan.scheduled_for), (Status.PENDING, None, None))
        detail = self.client.get(f"/plano/{plan.pk}/")
        self.assertContains(detail, "55.000 km")
        self.assertContains(detail, add_months(TODAY(), 12).strftime("%d/%m/%Y"))

    def test_one_off_plan_done_and_reverts_when_service_deleted(self):
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Instalar som")
        self.create_service(plan, plan=plan.pk, category="audio")
        plan.refresh_from_db()
        self.assertEqual(plan.status, Status.DONE)
        service = ServiceRecord.objects.get()
        self.client.post(f"/servicos/{service.pk}/excluir/")
        plan.refresh_from_db()
        self.assertEqual(plan.status, Status.PENDING)

    def test_unlinking_on_edit_refreshes_previous_plan(self):
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Instalar som")
        self.create_service(plan, plan=plan.pk, category="audio")
        service = ServiceRecord.objects.get()
        self.client.post(f"/servicos/{service.pk}/editar/", {"category": "audio", "kind": "preventive", "plan": "", **parts_data()})
        plan.refresh_from_db()
        self.assertEqual(plan.status, Status.PENDING)

    def test_link_existing_service(self):
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Óleo", interval_km=10000)
        service = ServiceRecord.objects.create(vehicle=self.vehicle, category="oil", date=TODAY(), kilometers=30000)
        self.client.post(f"/plano/{plan.pk}/vincular/", {"service": service.pk})
        service.refresh_from_db()
        self.assertEqual(service.plan, plan)
        self.assertContains(self.client.get(f"/plano/{plan.pk}/"), "40.000 km")

    def test_cannot_link_plan_or_service_of_other_vehicle(self):
        other_plan = MaintenancePlan.objects.create(vehicle=self.second, title="Etios")
        response = self.client.post("/servicos/novo/", {"category": "oil", "kind": "unspecified", "plan": other_plan.pk,
                                                        **parts_data()})
        self.assertFalse(ServiceRecord.objects.filter(plan=other_plan).exists())
        self.assertIn(response.status_code, (200, 302))
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Compacto")
        foreign_service = ServiceRecord.objects.create(vehicle=self.second, category="oil")
        self.client.post(f"/plano/{plan.pk}/vincular/", {"service": foreign_service.pk})
        foreign_service.refresh_from_db()
        self.assertIsNone(foreign_service.plan)


class PlanViewTests(PlanTestCase):
    def test_suggestions_have_no_intervals_and_are_idempotent(self):
        response = self.client.post("/plano/sugestoes/", {"keys": ["oil", "brake_fluid"]})
        self.assertRedirects(response, "/plano/")
        self.client.post("/plano/sugestoes/", {"keys": ["oil"]})
        plans = MaintenancePlan.objects.filter(vehicle=self.vehicle)
        self.assertEqual(plans.count(), 2)
        for plan in plans:
            self.assertIsNone(plan.interval_km)
            self.assertIsNone(plan.interval_months)
            self.assertFalse(plan.source_verified)
        self.assertTrue(plans.get(suggestion_key="oil").needs_validation)
        self.assertContains(self.client.get("/plano/sugestoes/"), "já está no plano")
        invalid = self.client.post("/plano/sugestoes/", {"keys": ["invalid"]})
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(plans.count(), 2)
        for suggestion in SUGGESTIONS:
            self.assertNotRegex(suggestion.reason, r"\d+\s*(km|mil|meses|anos)")

    def test_create_plan_validation(self):
        data = {"title": "Óleo", "kind": "manufacturer", "priority": "medium", "interval_km": "10000",
                "source_verified": "on", "source": ""}
        self.assertContains(self.client.post("/plano/novo/", data), "Informe a fonte")
        data["source"] = "Manual, p. 120"
        response = self.client.post("/plano/novo/", {**data, "estimated_cost": "R$ 250,00"})
        plan = MaintenancePlan.objects.get()
        self.assertRedirects(response, f"/plano/{plan.pk}/")
        self.assertFalse(plan.needs_validation)
        self.assertEqual(plan.estimated_cost, Decimal("250.00"))
        self.assertEqual(plan.vehicle, self.vehicle)

    def test_actions(self):
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="Alinhamento")
        url = f"/plano/{plan.pk}/"
        self.client.post(url + "programar/", {"scheduled_for": "2026-10-15"})
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.scheduled_for), (Status.SCHEDULED, date(2026, 10, 15)))
        response = self.client.post(url + "descartar/", {"dismissed_reason": ""}, follow=True)
        self.assertContains(response, "obrigatório")
        self.client.post(url + "descartar/", {"dismissed_reason": "Feito junto com pneus"})
        plan.refresh_from_db()
        self.assertEqual(plan.status, Status.DISMISSED)
        self.assertContains(self.client.get("/plano/?view=closed"), "Alinhamento")
        self.client.post(url + "reativar/")
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.dismissed_reason), (Status.PENDING, ""))
        self.assertEqual(self.client.get(url + "reativar/").status_code, 405)
        self.client.post(url + "excluir/")
        self.assertFalse(MaintenancePlan.objects.exists())

    def test_list_groups_and_estimate(self):
        self.reading(1, 51000)
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Atrasado", next_km=50000, estimated_cost=Decimal("100"))
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Sem ref")
        response = self.client.get("/plano/")
        self.assertContains(response, "Passaram da referência")
        self.assertContains(response, "Sem referência")
        self.assertContains(response, "R$ 100,00")

    def test_preferences(self):
        response = self.client.post("/alertas/configurar/", {"km_ahead": "500", "days_ahead": "15",
                                                             "reading_reminder_days": "20", "show_high": "on"})
        self.assertRedirects(response, "/alertas/")
        prefs = AlertPreferences.for_user(self.owner)
        self.assertEqual((prefs.km_ahead, prefs.show_low), (500, False))
        invalid = self.client.post("/alertas/configurar/", {"km_ahead": "-1", "days_ahead": "1",
                                                            "reading_reminder_days": "1"})
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(AlertPreferences.for_user(self.owner).km_ahead, 500)
        self.assertEqual(AlertPreferences.for_user(self.other).km_ahead, 1000)

    def test_dashboard_and_header_show_alerts(self):
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Fluido", next_date=TODAY() - timedelta(days=3),
                                       priority="high")
        response = self.client.get("/")
        self.assertContains(response, "Fluido: passou da referência")
        self.assertContains(response, 'class="badge-count"')
        self.assertContains(self.client.get("/alertas/"), "Fluido: passou da referência")

    def test_pages_render(self):
        plan = MaintenancePlan.objects.create(vehicle=self.vehicle, title="X", interval_months=6)
        for path in ["/plano/", "/plano/novo/", "/plano/sugestoes/", f"/plano/{plan.pk}/", f"/plano/{plan.pk}/editar/",
                     f"/plano/{plan.pk}/excluir/", "/alertas/", "/alertas/configurar/", "/plano/?view=closed",
                     f"/servicos/novo/?plano={plan.pk}"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_isolation(self):
        foreign = MaintenancePlan.objects.create(vehicle=self.foreign, title="Alheio")
        for path in [f"/plano/{foreign.pk}/", f"/plano/{foreign.pk}/editar/", f"/plano/{foreign.pk}/excluir/",
                     f"/plano/{foreign.pk}/programar/", f"/plano/{foreign.pk}/descartar/", f"/plano/{foreign.pk}/reativar/",
                     f"/plano/{foreign.pk}/vincular/", f"/servicos/novo/?plano={foreign.pk}"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, {}).status_code, 404)
        self.assertNotContains(self.client.get("/plano/"), "Alheio")
        self.assertTrue(MaintenancePlan.objects.filter(pk=foreign.pk).exists())
        self.client.logout()
        for path in ["/plano/", "/alertas/", "/alertas/configurar/", "/plano/sugestoes/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)
