from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from garage.models import Vehicle
from maintenance.models import Problem, ServiceRecord
from planning.catalog import SUGGESTIONS
from planning.models import MaintenancePlan

from .engine import analyze_symptom
from .knowledge import C, GENERIC, RED_FLAGS, RULES, normalize
from .models import UsageProfile

TODAY = timezone.localdate


class KnowledgeTests(SimpleTestCase):
    def test_normalize(self):
        self.assertEqual(normalize("Água na Direção"), "agua na direcao")

    def test_knowledge_has_no_numeric_intervals_or_definitive_claims(self):
        texts = [f"{cause.title} {cause.explanation} {cause.checks}" for cause in C.values()]
        texts += [question for rule in RULES for question in rule.questions]
        for text in texts:
            with self.subTest(text=text[:40]):
                self.assertNotRegex(text, r"\d+\s*(km|mil|meses|anos)")
                self.assertNotIn("com certeza", text.lower())
                self.assertNotIn("defeito confirmado", text.lower())

    def test_every_symptom_has_generic_causes(self):
        for symptom in Problem.Symptom.values:
            self.assertTrue(GENERIC.get(symptom))
        for rule in RULES:
            for term in rule.terms:
                self.assertEqual(term, normalize(term))
        for flag in RED_FLAGS:
            for term in flag.terms:
                self.assertEqual(term, normalize(term))


class EngineTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="owner")
        cls.other = user_model.objects.create_user(username="other")
        cls.vehicle = Vehicle.objects.create(owner=cls.owner, brand="Exemplo", model="Compacto", model_year=2020)
        cls.foreign = Vehicle.objects.create(owner=cls.other, brand="Other", model="Private", model_year=2020)

    def setUp(self):
        self.client.force_login(self.owner)

    def analyze(self, symptom, description, location="", severity="unknown", **kwargs):
        return analyze_symptom(self.vehicle, symptom, description, location, severity, TODAY(), **kwargs)


class EngineTests(EngineTestCase):
    def test_door_water_history_avoids_repeated_investigation(self):
        Problem.objects.create(vehicle=self.vehicle, symptom="noise", title="Barulho de água ao frear",
                               description="Barulho de água balançando nas frenagens.",
                               location="Porta traseira", status="resolved",
                               solution="Drenos da porta desobstruídos e água drenada.",
                               ruled_out="Não era o tanque de combustível.")
        analysis = self.analyze("noise", "Barulho de líquido na traseira ao frear", "Porta traseira")
        self.assertEqual(analysis.causes[0].key, "door_water")
        self.assertIn("fuel_slosh", [cause.key for cause in analysis.discarded])
        self.assertNotIn("fuel_slosh", [cause.key for cause in analysis.causes])
        self.assertTrue(any("água drenada" in note for note in analysis.history))
        self.assertTrue(analysis.questions[0].startswith("Da outra vez a solução foi"))

    def test_without_history_fuel_slosh_is_listed_as_possibly_normal(self):
        analysis = self.analyze("noise", "barulho de água chacoalhando ao frear")
        keys = [cause.key for cause in analysis.causes]
        self.assertIn("fuel_slosh", keys)
        self.assertTrue(C["fuel_slosh"].normal)
        self.assertFalse(analysis.discarded)

    def test_red_flags_raise_urgency_with_reason(self):
        cases = [("noise", "pedal baixo e barulho ao frear", "eficiência do freio"),
                 ("warning_light", "acendeu a luz do óleo", "pressão do óleo"),
                 ("leak", "cheiro de gasolina embaixo do carro", "combustível"),
                 ("warning_light", "luz vermelha de temperatura, parece que ferveu", "superaquecimento")]
        for symptom, text, reason in cases:
            with self.subTest(text=text):
                analysis = self.analyze(symptom, text)
                self.assertEqual(analysis.urgency, "high")
                self.assertTrue(any(reason in item for item in analysis.reasons))
                self.assertIn("evite rodar", analysis.advice)

    def test_safety_systems_are_medium_and_normal_things_low(self):
        brakes = self.analyze("noise", "chiado ao frear")
        self.assertEqual(brakes.urgency, "medium")
        self.assertEqual(brakes.causes[0].key, "brake_pads")
        ac = self.analyze("leak", "pinga água transparente sem cheiro com o ar-condicionado ligado")
        self.assertEqual(ac.urgency, "low")
        self.assertEqual(ac.causes[0].key, "ac_condensation")
        self.assertIn("costuma ser normal", ac.reasons[0])
        generic = self.analyze("other", "algo estranho")
        self.assertEqual(generic.causes[0].key, "generic")
        self.assertEqual(self.analyze("wear", "pintura desbotada", severity="high").urgency, "high")

    def test_history_context_services_audio_and_usage(self):
        ServiceRecord.objects.create(vehicle=self.vehicle, category="brakes", title="Troca de pastilhas",
                                     date=TODAY() - timedelta(days=20), warranty_until=TODAY() + timedelta(days=60),
                                     workshop="Oficina X")
        brakes = self.analyze("noise", "chiado ao frear")
        self.assertTrue(any("Troca de pastilhas" in note and "garantia" in note.lower() for note in brakes.history))
        self.assertIn("garantia", brakes.questions[0])
        ServiceRecord.objects.create(vehicle=self.vehicle, category="audio", title="Instalação de som")
        profile = UsageProfile.objects.create(vehicle=self.vehicle, parked_days=True)
        starting = self.analyze("starting", "carro não pega, só dá um clique", usage=profile)
        self.assertEqual(starting.causes[0].key, "battery")
        self.assertTrue(any("sistema de som" in note for note in starting.history))
        self.assertTrue(any("parado vários dias" in note for note in starting.history))

    def test_active_similar_problem_raises_to_medium(self):
        Problem.objects.create(vehicle=self.vehicle, symptom="electrical", description="Farol pisca sozinho",
                               location="Painel")
        analysis = self.analyze("electrical", "farol piscando de novo", "Painel")
        self.assertEqual(analysis.urgency, "medium")
        self.assertTrue(any("relato parecido em aberto" in reason for reason in analysis.reasons))


class ViewTests(EngineTestCase):
    def test_symptom_flow_and_save_as_problem(self):
        response = self.client.post("/assistente/sintoma/", {"symptom": "noise", "description": "chiado ao frear",
                                                              "location": "Dianteira esquerda", "severity": "medium"})
        self.assertContains(response, "Urgência estimada")
        self.assertContains(response, "Pastilhas de freio no fim da vida útil")
        self.assertContains(response, "Perguntas para levar ao mecânico")
        self.assertContains(response, "não substitui a avaliação de um mecânico")
        save_url = response.context["save_url"]
        form = self.client.get(save_url)
        self.assertContains(form, "chiado ao frear")
        self.assertContains(form, 'value="Dianteira esquerda"')
        self.assertEqual(form.context["form"].initial["symptom"], "noise")
        self.assertEqual(self.client.post("/assistente/sintoma/", {"symptom": "invalid"}).status_code, 200)
        self.assertEqual(Problem.objects.count(), 0)

    def test_problem_detail_and_analysis(self):
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="noise", description="estalo em buracos")
        detail = self.client.get(f"/problemas/{problem.pk}/")
        self.assertContains(detail, "Assistente: urgência média")
        analysis = self.client.get(f"/assistente/problema/{problem.pk}/")
        self.assertContains(analysis, "Componentes da suspensão com folga")
        problem.status = "resolved"
        problem.save()
        self.assertNotContains(self.client.get(f"/problemas/{problem.pk}/"), "Assistente: urgência")

    def test_home_review_groups_and_usage_tips(self):
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Óleo", kind="manufacturer",
                                       next_date=TODAY() - timedelta(days=1))
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Ruído na suspensão", kind="diagnosis")
        MaintenancePlan.objects.create(vehicle=self.vehicle, title="Correia", kind="manufacturer", suggestion_key="timing_belt")
        response = self.client.get("/assistente/")
        review = response.context["review"]
        groups = {kind: [plan.title for plan in plans] for kind, _, plans in review["groups"]}
        self.assertEqual(groups["manufacturer"], ["Óleo"])
        self.assertEqual(groups["diagnosis"], ["Ruído na suspensão"])
        self.assertIn("Correia", [plan.title for plan in review["no_history"]])
        self.assertIn("Troca do fluido de freio", [suggestion.title for suggestion in review["time_sensitive"]])
        self.assertEqual(review["missing_suggestions"], len(SUGGESTIONS) - 1)
        self.assertContains(response, "Informar perfil")
        self.client.post("/assistente/perfil/", {"parked_days": "on", "frequent_load": "on"})
        tips = self.client.get("/assistente/").context["review"]["tips"]
        self.assertEqual([tip.key for tip in tips], ["battery", "tires_check", "suspension"])
        self.client.post("/assistente/sugestao/battery/")
        self.assertTrue(MaintenancePlan.objects.filter(vehicle=self.vehicle, suggestion_key="battery").exists())
        self.assertTrue(self.client.get("/assistente/").context["review"]["tips"][0].in_plan)
        self.client.post("/assistente/sugestao/nao-existe/")
        self.assertEqual(self.client.get("/assistente/sugestao/battery/").status_code, 405)

    def test_mechanic_summary(self):
        self.vehicle.plate = "ABC1D23"
        self.vehicle.save()
        UsageProfile.objects.create(vehicle=self.vehicle, rough_roads=True)
        problem = Problem.objects.create(vehicle=self.vehicle, symptom="vibration", description="Volante vibra a 80 km/h",
                                         ruled_out="Balanceamento feito")
        ServiceRecord.objects.create(vehicle=self.vehicle, category="tires", title="Alinhamento", date=TODAY(),
                                     total_cost=Decimal("120"))
        response = self.client.get("/assistente/resumo/")
        for text in ("Resumo para o mecânico".upper(), "Volante vibra", "Balanceamento feito", "Rodas desbalanceadas",
                     "Alinhamento", "ruas esburacadas ou de terra", "Imprimir ou salvar PDF"):
            self.assertContains(response, text)
        self.assertEqual(problem.vehicle, self.vehicle)

    def test_isolation_and_login(self):
        foreign_problem = Problem.objects.create(vehicle=self.foreign, symptom="noise", description="Alheio")
        self.assertEqual(self.client.get(f"/assistente/problema/{foreign_problem.pk}/").status_code, 404)
        self.assertNotContains(self.client.get("/assistente/resumo/"), "Alheio")
        self.client.post("/assistente/perfil/", {"highway": "on"})
        self.assertFalse(UsageProfile.objects.filter(vehicle=self.foreign).exists())
        self.client.logout()
        for path in ("/assistente/", "/assistente/sintoma/", "/assistente/perfil/", "/assistente/resumo/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)

    def test_pages_render(self):
        for path in ("/assistente/", "/assistente/sintoma/", "/assistente/perfil/", "/assistente/resumo/", "/registrar/",
                     "/mais/", "/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
