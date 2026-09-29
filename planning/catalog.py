from dataclasses import dataclass

from .models import MaintenancePlan

Kind, Priority = MaintenancePlan.Kind, MaintenancePlan.Priority


@dataclass(frozen=True)
class Suggestion:
    key: str
    title: str
    category: str
    kind: str
    priority: str
    reason: str

    @property
    def kind_label(self):
        return MaintenancePlan.Kind(self.kind).label

# Deliberately without intervals: each owner fills them from the vehicle's own manual.
SUGGESTIONS = [
    Suggestion("oil", "Troca de óleo e filtro de óleo", "oil", Kind.MANUFACTURER, Priority.MEDIUM,
               "O manual define o intervalo em km e em meses e indica quando o uso é considerado severo."),
    Suggestion("general_review", "Revisão periódica", "general", Kind.MANUFACTURER, Priority.MEDIUM,
               "O plano de revisões do manual lista o que é verificado em cada etapa."),
    Suggestion("brake_fluid", "Troca do fluido de freio", "brakes", Kind.MANUFACTURER, Priority.HIGH,
               "O fluido absorve umidade com o tempo; o manual define o prazo de troca."),
    Suggestion("timing_belt", "Correia dentada e correias auxiliares", "belts", Kind.MANUFACTURER, Priority.HIGH,
               "Confira no manual se o motor usa correia dentada e o prazo de troca. Se usar, o rompimento pode danificar o motor."),
    Suggestion("coolant", "Líquido de arrefecimento", "cooling", Kind.MANUFACTURER, Priority.MEDIUM,
               "Confira o nível com o motor frio e o prazo de troca no manual."),
    Suggestion("air_filter", "Troca do filtro de ar do motor", "filters", Kind.MANUFACTURER, Priority.LOW,
               "Intervalo no manual; trajetos com poeira podem justificar inspeção mais frequente."),
    Suggestion("fuel_filter", "Troca do filtro de combustível", "fuel", Kind.MANUFACTURER, Priority.LOW,
               "Confira no manual se há troca periódica prevista para o seu motor."),
    Suggestion("cabin_filter", "Troca do filtro de cabine", "ac", Kind.MANUFACTURER, Priority.LOW,
               "Intervalo no manual. Mau cheiro ou ventilação fraca podem indicar filtro saturado."),
    Suggestion("spark_plugs", "Velas de ignição", "engine", Kind.MANUFACTURER, Priority.LOW,
               "Intervalo definido no manual."),
    Suggestion("brakes_check", "Inspeção de pastilhas, discos e freio de mão", "brakes", Kind.INSPECTION, Priority.HIGH,
               "O desgaste depende do uso; peça a medição nas revisões."),
    Suggestion("tires_check", "Pneus: calibragem, desgaste e estado", "tires", Kind.INSPECTION, Priority.HIGH,
               "Calibre conforme a etiqueta do veículo, considerando a carga transportada."),
    Suggestion("suspension", "Inspeção de suspensão e direção", "suspension", Kind.INSPECTION, Priority.MEDIUM,
               "Carga extra e vias irregulares aumentam o desgaste; peça avaliação nas revisões."),
    Suggestion("alignment", "Alinhamento e balanceamento", "tires", Kind.USAGE, Priority.MEDIUM,
               "Indicado ao trocar pneus, após impactos fortes ou se o volante vibrar ou puxar para um lado."),
    Suggestion("battery", "Teste da bateria", "battery", Kind.USAGE, Priority.MEDIUM,
               "Carro parado por vários dias descarrega a bateria; um teste de carga mostra o desgaste."),
    Suggestion("wipers", "Palhetas do limpador", "body", Kind.USAGE, Priority.LOW,
               "Troque quando deixarem marcas ou fizerem ruído, de preferência antes do período de chuvas."),
    Suggestion("door_drains", "Drenos das portas e vedações", "body", Kind.INSPECTION, Priority.LOW,
               "Drenos obstruídos acumulam água dentro das portas. Útil se já houve água em alguma porta."),
]
SUGGESTIONS_BY_KEY = {suggestion.key: suggestion for suggestion in SUGGESTIONS}
