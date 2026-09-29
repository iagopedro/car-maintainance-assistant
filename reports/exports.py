import csv
import io

from garage.models import OdometerReading
from maintenance.models import Problem, ServiceRecord
from planning.models import MaintenancePlan

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    if hasattr(value, "quantize"):
        return f"{value:.2f}".replace(".", ",")
    text = str(value)
    # Spreadsheet apps execute cells that start like formulas (CSV injection).
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def services(owner):
    yield ["Veículo", "Data", "Km", "Categoria", "Tipo", "O que foi feito", "Oficina", "Peças (R$)",
           "Mão de obra (R$)", "Total (R$)", "Garantia até", "Peças substituídas", "Item do plano", "Descrição",
           "Observações"]
    queryset = (ServiceRecord.objects.filter(vehicle__owner=owner).select_related("vehicle", "plan")
                .prefetch_related("parts").order_by("vehicle_id", "date", "pk"))
    for service in queryset:
        parts = "; ".join(f"{part.name} ({part.brand_model})" if part.brand_model else part.name
                          for part in service.parts.all())
        yield [service.vehicle, service.date, service.kilometers, service.get_category_display(),
               service.get_kind_display(), service.display_title, service.workshop, service.parts_cost,
               service.labor_cost, service.total_cost, service.warranty_until, parts,
               service.plan.title if service.plan else "", service.description, service.notes]


def problems(owner):
    yield ["Veículo", "Data do relato", "Km", "Sintoma", "Título", "Local", "Sistema", "Gravidade percebida",
           "Situação", "Diagnóstico", "Causas descartadas", "Solução", "Resolvido em", "Serviço relacionado", "Relato"]
    queryset = (Problem.objects.filter(vehicle__owner=owner).select_related("vehicle", "resolved_by_service")
                .order_by("vehicle_id", "reported_on", "pk"))
    for problem in queryset:
        yield [problem.vehicle, problem.reported_on, problem.kilometers, problem.get_symptom_display(),
               problem.display_title, problem.location, problem.get_category_display(), problem.get_severity_display(),
               problem.get_status_display(), problem.diagnosis, problem.ruled_out, problem.solution,
               problem.resolved_on, problem.resolved_by_service.display_title if problem.resolved_by_service else "",
               problem.description]


def readings(owner):
    yield ["Veículo", "Data", "Km", "Origem", "Observação"]
    queryset = OdometerReading.objects.filter(vehicle__owner=owner).select_related("vehicle").order_by("vehicle_id", "date")
    for reading in queryset:
        yield [reading.vehicle, reading.date, reading.kilometers, reading.get_source_display(), reading.notes]


def plans(owner):
    yield ["Veículo", "Item", "Tipo", "Prioridade", "Situação", "A cada (km)", "A cada (meses)", "Próxima (km)",
           "Próxima (data)", "Programado para", "Fonte", "Fonte conferida", "Custo estimado (R$)", "Motivo",
           "Motivo do descarte"]
    queryset = MaintenancePlan.objects.filter(vehicle__owner=owner).select_related("vehicle").order_by("vehicle_id", "title")
    for plan in queryset:
        yield [plan.vehicle, plan.title, plan.get_kind_display(), plan.get_priority_display(), plan.get_status_display(),
               plan.interval_km, plan.interval_months, plan.next_km, plan.next_date, plan.scheduled_for, plan.source,
               plan.source_verified, plan.estimated_cost, plan.reason, plan.dismissed_reason]


EXPORTS = {
    "servicos": ("Serviços", services),
    "problemas": ("Problemas", problems),
    "quilometragem": ("Quilometragem", readings),
    "plano": ("Plano de manutenção", plans),
}


def render_csv(rows):
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    for row in rows:
        writer.writerow([cell(value) for value in row])
    return buffer.getvalue()
