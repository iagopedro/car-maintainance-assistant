import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from .models import OdometerReading, Vehicle

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
PDF = b"%PDF-1.4\n%test\n"


def has_horizontal_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth > innerWidth")


@skipUnless(os.environ.get("RUN_BROWSER_TESTS") == "1", "Set RUN_BROWSER_TESTS=1 to run Playwright.")
class BrowserJourneyTests(StaticLiveServerTestCase):
    def test_owner_journey_desktop_and_mobile(self):
        from playwright.sync_api import expect, sync_playwright

        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        today = timezone.localdate()
        previous_date = (today - timedelta(days=30)).isoformat()
        errors = []
        failed_responses = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="pt-BR")
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_responses.append(response.url) if response.status >= 400 else None)
            page.goto(self.live_server_url)
            expect(page.get_by_role("heading", name="Criar sua conta")).to_be_visible()
            page.locator("#id_username").fill("browser-owner")
            page.locator("#id_password1").fill("Browser-test-only-83746!")
            page.locator("#id_password2").fill("Browser-test-only-83746!")
            page.get_by_role("button", name="Criar conta", exact=True).click()
            page.get_by_role("link", name="Cadastrar veículo de exemplo").click()
            expect(page.locator("#id_model")).to_have_value("Compacto")
            expect(page.locator("#id_initial_kilometers")).to_have_value("")
            expect(page.locator("#id_engine_verified")).not_to_be_checked()
            page.locator("#id_initial_kilometers").fill("45000")
            page.get_by_role("button", name="Cadastrar veículo").click()
            expect(page.get_by_role("heading", name="Exemplo Compacto 2022")).to_be_visible()
            vehicle_path = urlparse(page.url).path
            page.get_by_role("link", name="Editar dados").click()
            page.locator("#id_version").fill("Versão ainda a confirmar")
            page.get_by_role("button", name="Salvar alterações").click()
            expect(page.get_by_text("Exemplo Compacto 2022", exact=False).first).to_be_visible()
            page.get_by_role("link", name="Registrar km").click()
            page.locator("#id_kilometers").fill("44000")
            page.locator("#id_date").fill(previous_date)
            page.locator("#id_source").select_option("document")
            page.get_by_role("button", name="Salvar leitura").click()
            expect(page.locator("tbody tr")).to_have_count(2)
            page.locator("#id_source").select_option("document")
            page.get_by_role("button", name="Filtrar", exact=True).click()
            expect(page.locator("tbody tr")).to_have_count(1)
            page.reload()
            expect(page.get_by_role("heading", name="Histórico de km")).to_be_visible()
            expect(page.locator("tbody tr")).to_have_count(1)
            page.get_by_role("link", name="Registrar km").click()
            page.locator("#id_kilometers").fill("46000")
            page.locator("#id_date").fill((today - timedelta(days=15)).isoformat())
            page.get_by_role("button", name="Salvar leitura").click()
            expect(page.locator("#id_kilometers_errors")).to_contain_text("maior que a leitura")
            page.get_by_role("link", name="Visão geral").click()
            expect(page.locator(".odometer-display")).to_contain_text("45.000")
            page.screenshot(path=str(artifacts / "dashboard-desktop.png"), full_page=True, animations="disabled")
            paths = ["/", "/veiculos/", vehicle_path, f"{vehicle_path}editar/",
                     f"{vehicle_path}quilometragem/", f"{vehicle_path}quilometragem/nova/", "/conta/senha/"]
            for width in (360, 390, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                for path in paths:
                    page.goto(self.live_server_url + path)
                    with self.subTest(width=width, path=path):
                        self.assertFalse(has_horizontal_overflow(page))
                        self.assertGreater(page.locator("svg.lucide").count(), 0)
                        expect(page.locator("h1")).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(self.live_server_url)
            page.screenshot(path=str(artifacts / "dashboard-mobile.png"), full_page=True, animations="disabled")
            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Garagem").click()
            page.get_by_role("link", name="Novo veículo").click()
            page.locator("#id_brand").fill("Toyota")
            page.locator("#id_model").fill("Etios")
            page.locator("#id_model_year").fill("2018")
            page.get_by_role("button", name="Cadastrar veículo").click()
            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Garagem").click()
            page.locator(".vehicle-card").filter(has_text="Exemplo Compacto").get_by_role("button", name="Usar no painel").click()
            expect(page.locator(".vehicle-overview")).to_contain_text("Exemplo Compacto")
            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Alterar senha").click()
            page.locator("#id_old_password").fill("Browser-test-only-83746!")
            page.locator("#id_new_password1").fill("Changed-browser-only-64937!")
            page.locator("#id_new_password2").fill("Changed-browser-only-64937!")
            page.get_by_role("button", name="Salvar senha").click()
            expect(page.get_by_role("heading", name="Senha atualizada")).to_be_visible()
            page.get_by_role("button", name="Sair", exact=True).click()
            expect(page.get_by_role("heading", name="Entrar na conta")).to_be_visible()
            page.locator("#id_username").fill("browser-owner")
            page.locator("#id_password").fill("Changed-browser-only-64937!")
            page.get_by_role("button", name="Entrar", exact=True).click()
            expect(page.get_by_role("heading", name="Visão geral")).to_be_visible()
            self.assertEqual(errors, [])
            self.assertEqual(failed_responses, [])
            browser.close()

    def test_mobile_service_and_problem_journey(self):
        from playwright.sync_api import expect, sync_playwright

        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        password = "Mobile-test-only-58302!"
        owner = get_user_model().objects.create_user("mobile-owner", password=password)
        vehicle = Vehicle.objects.create(owner=owner, brand="Exemplo", model="Compacto", model_year=2022)
        OdometerReading.objects.create(vehicle=vehicle, date=timezone.localdate() - timedelta(days=30), kilometers=44000)
        errors, failed_responses = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True, has_touch=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_responses.append(response.url) if response.status >= 400 else None)
            page.goto(self.live_server_url + "/conta/entrar/")
            page.locator("#id_username").fill("mobile-owner")
            page.locator("#id_password").fill(password)
            page.get_by_role("button", name="Entrar", exact=True).click()
            expect(page.locator(".main-nav")).to_be_hidden()

            page.locator(".bottom-nav").get_by_role("link", name="Registrar").click()
            page.get_by_role("link", name="Serviço ou manutenção").click()
            expect(page.locator("#id_date")).to_have_value(timezone.localdate().isoformat())
            expect(page.locator(".more-details")).not_to_have_attribute("open", "")
            page.locator("#id_category").select_option("oil")
            page.locator("#id_title").fill("Troca de óleo e filtro de óleo")
            page.locator("#id_kilometers").fill("45000")
            page.locator("#id_total_cost").fill("189,90")
            page.locator("#id_attachments").set_input_files([{"name": "nota.png", "mimeType": "image/png", "buffer": PNG}])
            page.get_by_text("Mais detalhes").click()
            page.locator(".chip").filter(has_text="Preventiva").click()
            page.locator("#id_parts-0-name").fill("Filtro de óleo")
            page.get_by_role("button", name="Adicionar outra peça").click()
            expect(page.locator("#id_parts-1-name")).to_be_focused()
            page.locator("#id_parts-1-name").fill("Óleo 5W30")
            expect(page.get_by_role("button", name="Salvar serviço")).to_be_in_viewport()
            page.get_by_role("button", name="Salvar serviço").click()
            expect(page.get_by_role("heading", name="Troca de óleo e filtro de óleo")).to_be_visible()
            expect(page.get_by_text("Quilometragem atual atualizada para 45.000 km.")).to_be_visible()
            expect(page.locator(".parts-list li")).to_have_count(2)
            self.assertTrue(page.locator(".attachment-card img").evaluate("img => img.complete && img.naturalWidth > 0"))
            page.locator(".upload-button input").set_input_files([{"name": "orcamento.pdf", "mimeType": "application/pdf", "buffer": PDF}])
            expect(page.locator(".attachment-card")).to_have_count(2)
            page.screenshot(path=str(artifacts / "service-detail-mobile.png"), full_page=True, animations="disabled")
            service_path = urlparse(page.url).path

            page.locator(".bottom-nav").get_by_role("link", name="Problemas").click()
            page.get_by_role("link", name="Registrar esse caso").click()
            expect(page.locator(".more-details")).to_have_attribute("open", "")
            page.get_by_role("button", name="Salvar problema").click()
            expect(page.get_by_text("Causas já descartadas")).to_be_visible()
            expect(page.locator(".tag-row .status")).to_have_text("Resolvido")

            page.locator(".bottom-nav").get_by_role("link", name="Registrar").click()
            page.get_by_role("link", name="Problema ou sintoma").click()
            page.locator(".chip").filter(has_text="Vibração").click()
            page.locator("#id_description").fill("Volante vibra acima de 80 km/h.")
            page.locator(".chip").filter(has_text="Média").click()
            page.get_by_role("button", name="Salvar problema").click()
            expect(page.locator(".tag-row .status")).to_have_text("Aberto")
            page.locator("#id_note").fill("Oficina fez o balanceamento e a vibração sumiu.")
            page.locator("#id_status").select_option("resolved")
            page.get_by_role("button", name="Salvar acompanhamento").click()
            expect(page.locator(".tag-row .status")).to_have_text("Resolvido")
            expect(page.locator(".solution-section")).to_contain_text("balanceamento")
            page.screenshot(path=str(artifacts / "problem-detail-mobile.png"), full_page=True, animations="disabled")
            problem_path = urlparse(page.url).path

            page.locator(".bottom-nav").get_by_role("link", name="Início").click()
            expect(page.locator(".odometer-display")).to_contain_text("45.000")
            expect(page.locator(".record-list").first).to_contain_text("R$ 189,90")
            page.screenshot(path=str(artifacts / "dashboard-services-mobile.png"), full_page=True, animations="disabled")

            page.locator(".bottom-nav").get_by_role("link", name="Serviços").click()
            page.locator("#id_category").select_option("tires")
            expect(page.get_by_role("heading", name="Nenhum serviço encontrado")).to_be_visible()
            self.assertIn("category=tires", page.url)

            for width in (360, 390, 1280):
                page.set_viewport_size({"width": width, "height": 800})
                for path in ("/", "/registrar/", "/servicos/", "/servicos/novo/", service_path, f"{service_path}editar/",
                             "/problemas/", "/problemas/novo/", problem_path, f"{problem_path}editar/"):
                    page.goto(self.live_server_url + path)
                    with self.subTest(width=width, path=path):
                        self.assertFalse(has_horizontal_overflow(page))
                        expect(page.locator("h1")).to_be_visible()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(self.live_server_url + service_path)
            page.screenshot(path=str(artifacts / "service-detail-desktop.png"), full_page=True, animations="disabled")
            page.get_by_role("link", name="Excluir").click()
            page.get_by_role("button", name="Excluir definitivamente").click()
            expect(page.get_by_text("Serviço excluído.")).to_be_visible()
            page.goto(self.live_server_url)
            expect(page.locator(".odometer-display")).to_contain_text("44.000")
            self.assertEqual(errors, [])
            self.assertEqual(failed_responses, [])
            browser.close()

    def test_plan_and_alerts_journey(self):
        from playwright.sync_api import expect, sync_playwright

        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        password = "Plan-test-only-71925!"
        owner = get_user_model().objects.create_user("plan-owner", password=password)
        vehicle = Vehicle.objects.create(owner=owner, brand="Exemplo", model="Compacto", model_year=2022)
        today = timezone.localdate()
        OdometerReading.objects.create(vehicle=vehicle, date=today - timedelta(days=10), kilometers=44000)
        errors, failed_responses = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True, has_touch=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_responses.append(response.url) if response.status >= 400 else None)
            page.goto(self.live_server_url + "/conta/entrar/")
            page.locator("#id_username").fill("plan-owner")
            page.locator("#id_password").fill(password)
            page.get_by_role("button", name="Entrar", exact=True).click()
            expect(page.get_by_text("Monte seu plano de manutenção")).to_be_visible()

            page.locator(".bottom-nav").get_by_role("link", name="Plano").click()
            page.get_by_role("link", name="Ver sugestões").first.click()
            for title in ("Troca de óleo e filtro de óleo", "Teste da bateria"):
                page.locator(".suggestion-item").filter(has_text=title).locator("input").check()
            page.get_by_role("button", name="Adicionar selecionados").click()
            expect(page.get_by_text("2 itens adicionados")).to_be_visible()
            expect(page.locator("#grupo-unknown .record-item")).to_have_count(2)

            page.get_by_role("link", name="Troca de óleo e filtro de óleo").click()
            expect(page.get_by_text("Recomendação do fabricante ainda não conferida")).to_be_visible()
            page.get_by_role("link", name="Editar").click()
            page.locator("#id_interval_km").fill("10000")
            page.locator("#id_interval_months").fill("12")
            page.locator("#id_source").fill("Manual do proprietário")
            page.locator("#id_source_verified").check()
            page.get_by_role("button", name="Salvar item").click()
            expect(page.get_by_text("ainda não conferida")).to_have_count(0)
            expect(page.locator(".due-box")).to_contain_text("Sem data ou km de referência")

            page.get_by_role("link", name="Registrar última realização").click()
            expect(page.locator("#id_title")).to_have_value("Troca de óleo e filtro de óleo")
            page.locator("#id_date").fill((today - timedelta(days=60)).isoformat())
            page.locator("#id_kilometers").fill("34500")
            page.get_by_role("button", name="Salvar serviço").click()
            expect(page.get_by_text("Item do plano")).to_be_visible()

            page.locator(".bottom-nav").get_by_role("link", name="Início").click()
            expect(page.locator(".alerts-section")).to_contain_text("Troca de óleo e filtro de óleo: está chegando")
            expect(page.locator(".alerts-section")).to_contain_text("faltam 500 km")
            expect(page.locator(".alert-button .badge-count")).to_be_visible()
            page.screenshot(path=str(artifacts / "dashboard-alerts-mobile.png"), full_page=True, animations="disabled")

            page.locator(".bottom-nav").get_by_role("link", name="Plano").click()
            expect(page.locator("#grupo-soon")).to_contain_text("Troca de óleo")
            page.screenshot(path=str(artifacts / "plan-list-mobile.png"), full_page=True, animations="disabled")
            page.get_by_role("link", name="Teste da bateria").click()
            page.get_by_text("Programar data na oficina").click()
            page.locator("#id_scheduled_for").fill((today + timedelta(days=7)).isoformat())
            page.get_by_role("button", name="Programar", exact=True).click()
            expect(page.locator(".due-box")).to_contain_text("Programado para")
            plan_path = urlparse(page.url).path
            page.screenshot(path=str(artifacts / "plan-detail-mobile.png"), full_page=True, animations="disabled")

            page.locator(".alert-button").click()
            expect(page.locator(".alert-list")).to_contain_text("Troca de óleo")
            page.get_by_role("link", name="Configurar").click()
            page.locator("#id_show_medium").uncheck()
            page.get_by_role("button", name="Salvar", exact=True).click()
            expect(page.get_by_text("Preferências de alerta salvas.")).to_be_visible()
            expect(page.get_by_text("Troca de óleo e filtro de óleo: está chegando")).to_have_count(0)

            for width in (360, 800, 1024, 1280):
                page.set_viewport_size({"width": width, "height": 800})
                for path in ("/", "/plano/", "/plano/sugestoes/", "/plano/novo/", plan_path, f"{plan_path}editar/",
                             "/alertas/", "/alertas/configurar/", "/servicos/", "/problemas/"):
                    page.goto(self.live_server_url + path)
                    with self.subTest(width=width, path=path):
                        self.assertFalse(has_horizontal_overflow(page))
                        expect(page.locator("h1")).to_be_visible()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(self.live_server_url + "/plano/")
            page.screenshot(path=str(artifacts / "plan-list-desktop.png"), full_page=True, animations="disabled")
            self.assertEqual(errors, [])
            self.assertEqual(failed_responses, [])
            browser.close()

    def test_history_finance_and_data_journey(self):
        from playwright.sync_api import expect, sync_playwright

        from maintenance.models import Problem, ServiceRecord
        from planning.models import MaintenancePlan

        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        today = timezone.localdate()
        password = "Data-test-only-40517!"
        user_model = get_user_model()
        owner = user_model.objects.create_user("data-owner", password=password)
        user_model.objects.create_user("new-install", password=password)
        vehicle = Vehicle.objects.create(owner=owner, brand="Exemplo", model="Compacto", model_year=2022)
        OdometerReading.objects.create(vehicle=vehicle, date=today - timedelta(days=90), kilometers=40000)
        OdometerReading.objects.create(vehicle=vehicle, date=today - timedelta(days=1), kilometers=43000)
        ServiceRecord.objects.create(vehicle=vehicle, category="oil", kind="preventive", title="Troca de óleo",
                                     date=today - timedelta(days=20), total_cost=Decimal("189.90"))
        ServiceRecord.objects.create(vehicle=vehicle, category="suspension", kind="corrective", title="Bieleta",
                                     date=today - timedelta(days=50), total_cost=Decimal("320"))
        Problem.objects.create(vehicle=vehicle, symptom="noise", description="Estalo na suspensão",
                               reported_on=today - timedelta(days=60), status="resolved")
        MaintenancePlan.objects.create(vehicle=vehicle, title="Fluido de freio", next_date=today + timedelta(days=40),
                                       estimated_cost=Decimal("150"))
        errors, failed_responses = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True,
                                    has_touch=True, accept_downloads=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_responses.append(response.url) if response.status >= 400 else None)

            def login(username):
                page.goto(self.live_server_url + "/conta/entrar/")
                page.locator("#id_username").fill(username)
                page.locator("#id_password").fill(password)
                page.get_by_role("button", name="Entrar", exact=True).click()

            login("data-owner")
            expect(page.locator(".metrics-row")).to_contain_text("R$ 509,90")
            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Linha do tempo").click()
            expect(page.locator(".timeline-upcoming")).to_contain_text("Fluido de freio")
            expect(page.locator(".tl-month .tl-item")).to_have_count(5)
            page.locator("#id_type").select_option("services")
            expect(page.locator(".tl-month .tl-item")).to_have_count(2)
            expect(page.locator(".timeline-upcoming")).to_have_count(0)
            self.assertIn("type=services", page.url)
            page.screenshot(path=str(artifacts / "timeline-mobile.png"), full_page=True, animations="disabled")

            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Finanças").click()
            expect(page.locator(".finance-summary")).to_contain_text("R$ 509,90")
            expect(page.locator(".forecast")).to_contain_text("R$ 150,00")
            expect(page.locator(".bar-list").first).to_contain_text("Corretiva")
            page.screenshot(path=str(artifacts / "finance-mobile.png"), full_page=True, animations="disabled")

            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Seus dados").click()
            with page.expect_download() as csv_info:
                page.locator(".csv-links").get_by_role("link", name="Serviços").click()
            csv_text = Path(csv_info.value.path()).read_text(encoding="utf-8")
            self.assertTrue(csv_text.startswith("\ufeffVeículo;"))
            self.assertIn("189,90", csv_text)
            with page.expect_download() as backup_info:
                page.get_by_role("button", name="Baixar backup").click()
            backup_path = artifacts / "backup-e2e.zip"
            backup_info.value.save_as(str(backup_path))

            page.goto(self.live_server_url + "/mais/")
            page.get_by_role("button", name="Sair").click()
            login("new-install")
            page.get_by_role("link", name="Restaurar seus dados").click()
            page.locator("#id_backup").set_input_files(str(backup_path))
            page.locator("#id_confirm").check()
            page.get_by_role("button", name="Restaurar").click()
            expect(page.get_by_text("Backup restaurado: 1 veículo(s), 2 serviço(s)")).to_be_visible()
            expect(page.locator(".odometer-display")).to_contain_text("43.000")
            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Seus dados").click()
            expect(page.get_by_text("Disponível apenas em uma conta sem veículos")).to_be_visible()

            for width in (360, 800, 1024, 1180, 1280, 1440):
                page.set_viewport_size({"width": width, "height": 800})
                for path in ("/", "/historico/", "/financas/", "/financas/?periodo=all", "/dados/", "/mais/", "/plano/"):
                    page.goto(self.live_server_url + path)
                    with self.subTest(width=width, path=path):
                        self.assertFalse(has_horizontal_overflow(page))
                        expect(page.locator("h1")).to_be_visible()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(self.live_server_url + "/financas/")
            page.screenshot(path=str(artifacts / "finance-desktop.png"), full_page=True, animations="disabled")
            self.assertEqual(errors, [])
            self.assertEqual(failed_responses, [])
            browser.close()

    def test_assistant_journey(self):
        from playwright.sync_api import expect, sync_playwright

        from maintenance.models import Problem

        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        password = "Assistant-test-only-26814!"
        owner = get_user_model().objects.create_user("assistant-owner", password=password)
        vehicle = Vehicle.objects.create(owner=owner, brand="Exemplo", model="Compacto", model_year=2022)
        OdometerReading.objects.create(vehicle=vehicle, date=timezone.localdate() - timedelta(days=5), kilometers=45000)
        Problem.objects.create(vehicle=vehicle, symptom="noise", title="Ruído de líquido ao frear",
                               description="Ruído de líquido na região traseira durante frenagens.", location="Porta traseira",
                               status="resolved", solution="Água drenada da porta traseira.",
                               ruled_out="Não relacionado ao sistema de combustível, bomba ou injeção.")
        errors, failed_responses = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True, has_touch=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_responses.append(response.url) if response.status >= 400 else None)
            page.goto(self.live_server_url + "/conta/entrar/")
            page.locator("#id_username").fill("assistant-owner")
            page.locator("#id_password").fill(password)
            page.get_by_role("button", name="Entrar", exact=True).click()
            expect(page.locator(".assistant-banner")).to_be_visible()

            page.locator(".bottom-nav").get_by_role("link", name="Registrar").click()
            page.get_by_role("link", name="Não sei o que é: perguntar ao assistente").click()
            page.locator(".chip").filter(has_text="Ruído").click()
            page.locator("#id_description").fill("Barulho de líquido na traseira quando freio")
            page.locator("#id_location").fill("Porta traseira")
            page.get_by_role("button", name="Analisar").click()
            expect(page.locator(".urgency-box")).to_be_visible()
            expect(page.locator(".cause-item").first).to_contain_text("Água acumulada dentro da porta")
            expect(page.locator(".discarded-box")).to_contain_text("Movimento do combustível no tanque")
            expect(page.locator(".questions-box")).to_contain_text("Da outra vez a solução foi")
            page.screenshot(path=str(artifacts / "assistant-symptom-mobile.png"), full_page=True, animations="disabled")
            page.get_by_role("link", name="Salvar como problema").click()
            expect(page.locator("#id_description")).to_have_value("Barulho de líquido na traseira quando freio")
            page.get_by_role("button", name="Salvar problema").click()
            expect(page.locator(".assistant-card")).to_contain_text("Assistente: urgência")
            page.get_by_role("link", name="Ver possibilidades e perguntas para o mecânico").click()
            expect(page.locator(".cause-item").first).to_contain_text("Água acumulada")

            page.get_by_role("link", name="Mais opções").click()
            page.get_by_role("link", name="Assistente de manutenção").click()
            page.get_by_role("link", name="Informar perfil").click()
            page.get_by_text("Fica parado vários dias seguidos").click()
            page.get_by_role("button", name="Salvar perfil").click()
            expect(page.locator(".tip-item").first).to_contain_text("Teste da bateria")
            page.locator(".tip-item").first.get_by_role("button", name="Adicionar ao plano").click()
            expect(page.get_by_text("adicionado ao plano")).to_be_visible()
            expect(page.locator(".tip-item").first).to_contain_text("No plano")
            page.screenshot(path=str(artifacts / "assistant-home-mobile.png"), full_page=True, animations="disabled")

            page.get_by_role("link", name="Resumo para o mecânico").click()
            expect(page.locator(".summary-problem")).to_contain_text("Barulho de líquido")
            expect(page.locator(".summary-block").first).to_contain_text("fica parado vários dias seguidos")
            page.emulate_media(media="print")
            expect(page.locator(".bottom-nav")).to_be_hidden()
            expect(page.locator(".site-header")).to_be_hidden()
            page.emulate_media(media="screen")

            for width in (360, 1024, 1180, 1220, 1300, 1440, 1500):
                page.set_viewport_size({"width": width, "height": 800})
                for path in ("/", "/assistente/", "/assistente/sintoma/", "/assistente/resumo/", "/historico/", "/plano/"):
                    page.goto(self.live_server_url + path)
                    with self.subTest(width=width, path=path):
                        self.assertFalse(has_horizontal_overflow(page))
                        expect(page.locator("h1")).to_be_visible()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(self.live_server_url + "/assistente/")
            page.screenshot(path=str(artifacts / "assistant-home-desktop.png"), full_page=True, animations="disabled")
            self.assertEqual(errors, [])
            self.assertEqual(failed_responses, [])
            browser.close()