import re
from dataclasses import dataclass, field
from datetime import timedelta

from django.urls import reverse

from maintenance.models import Category, Problem
from planning.catalog import SUGGESTIONS_BY_KEY
from planning.models import MaintenancePlan
from planning.rules import fmt_km

from .knowledge import (GENERAL_QUESTIONS, GENERIC, GENERIC_QUESTIONS, RED_FLAGS, RULES, SAFETY_CATEGORIES, normalize)

URGENCY = {
    "high": ("Alta", "Se houver risco à segurança, evite rodar e procure avaliação profissional o quanto antes."),
    "medium": ("Média", "Agende uma avaliação nos próximos dias."),
    "low": ("Baixa", "Acompanhe e mencione na próxima revisão."),
}
STOPWORDS = {"quando", "depois", "sempre", "lado", "direito", "esquerdo", "carro", "tambem", "muito", "pouco", "ainda"}
RELATED_WINDOW_DAYS = 365


@dataclass
class SymptomAnalysis:
    urgency: str = "low"
    reasons: list = field(default_factory=list)
    causes: list = field(default_factory=list)
    discarded: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    history: list = field(default_factory=list)

    @property
    def urgency_label(self):
        return URGENCY[self.urgency][0]

    @property
    def advice(self):
        return URGENCY[self.urgency][1]


def words(text):
    return {word for word in re.findall(r"[a-z]{5,}", normalize(text)) if word not in STOPWORDS}


def similar_problems(vehicle, symptom, description, location, exclude_pk):
    location_key = normalize(location).strip()
    base_words = words(description)
    matches = []
    for problem in vehicle.problems.exclude(pk=exclude_pk).filter(symptom=symptom):
        same_place = location_key and normalize(problem.location).strip() == location_key
        if same_place or len(base_words & words(problem.description)) >= 2:
            matches.append(problem)
    return matches


def raise_to(analysis, level, reason):
    order = ["low", "medium", "high"]
    if order.index(level) > order.index(analysis.urgency):
        analysis.urgency = level
    if reason not in analysis.reasons:
        analysis.reasons.append(reason)


def matched_causes(symptom, text):
    causes, questions = [], []
    for rule in RULES:
        if symptom in rule.symptoms and any(term in text for term in rule.terms):
            causes.extend(rule.causes)
            questions.extend(rule.questions)
    if not causes:
        causes.extend(GENERIC.get(symptom, GENERIC["other"]))
        questions.extend(GENERIC_QUESTIONS.get(symptom, ()))
    unique = list({cause.key: cause for cause in causes}.values())
    return unique, questions


def analyze_symptom(vehicle, symptom, description, location="", severity="unknown", today=None, exclude_pk=None,
                    usage=None):
    text = normalize(f"{description} {location}")
    causes, questions = matched_causes(symptom, text)
    analysis = SymptomAnalysis()
    similar = similar_problems(vehicle, symptom, description, location, exclude_pk)
    ruled_out_text = " ".join(normalize(problem.ruled_out) for problem in similar)
    for cause in causes:
        if cause.ruled_out_terms and any(term in ruled_out_text for term in cause.ruled_out_terms):
            analysis.discarded.append(cause)
        else:
            analysis.causes.append(cause)
    for problem in similar:
        when = f"{problem.reported_on:%d/%m/%Y}" if problem.reported_on else "data desconhecida"
        note = f"Relato parecido ({when}): {problem.display_title}. Situação: {problem.get_status_display().lower()}."
        if problem.solution:
            note += f" Solução: {problem.solution}"
            questions.insert(0, f"Da outra vez a solução foi: {problem.solution[:120].rstrip('. ')}. Pode ser a mesma causa?")
        if problem.ruled_out:
            note += f" Causas descartadas: {problem.ruled_out}"
        analysis.history.append(note)
    if symptom in ("electrical", "starting") and vehicle.services.filter(category=Category.AUDIO).exists():
        analysis.history.append("Há serviço de sistema de som registrado; instalações adicionais podem influenciar a "
                                "bateria e a parte elétrica.")
    if usage and usage.parked_days and symptom in ("starting", "electrical"):
        analysis.history.append("Você informou que o carro fica parado vários dias; isso reduz a carga da bateria.")
    add_related_services(vehicle, analysis, today)
    for flag in RED_FLAGS:
        if any(term in text for term in flag.terms):
            raise_to(analysis, "high", flag.reason)
    if symptom == "warning_light" and "vermelh" in text:
        raise_to(analysis, "high", "Luz de advertência vermelha no painel.")
    if severity == Problem.Severity.HIGH:
        raise_to(analysis, "high", "Você marcou gravidade alta.")
    relevant = [cause for cause in analysis.causes if not cause.normal]
    if any(cause.category in SAFETY_CATEGORIES for cause in relevant):
        raise_to(analysis, "medium", "Pode envolver freios, direção, suspensão ou pneus, itens de segurança.")
    if any(problem.is_active for problem in similar):
        raise_to(analysis, "medium", "Já existe um relato parecido em aberto.")
    if severity == Problem.Severity.MEDIUM:
        raise_to(analysis, "medium", "Você marcou gravidade média.")
    if not analysis.reasons:
        analysis.reasons.append("A possibilidade mais comum costuma ser normal; confirme na próxima revisão."
                                if analysis.causes and analysis.causes[0].normal else
                                "Não há sinais de risco imediato nos dados informados.")
    analysis.questions = list(dict.fromkeys([*analysis.questions, *questions, *GENERAL_QUESTIONS]))
    return analysis


def add_related_services(vehicle, analysis, today):
    categories = {cause.category for cause in analysis.causes}
    if not categories or today is None:
        return
    recent = vehicle.services.filter(category__in=categories, date__gte=today - timedelta(days=RELATED_WINDOW_DAYS))
    for service in recent[:3]:
        note = f"Serviço relacionado em {service.date:%d/%m/%Y}: {service.display_title}"
        if service.workshop:
            note += f" ({service.workshop})"
        if service.warranty_active:
            note += f". Em garantia até {service.warranty_until:%d/%m/%Y}."
            analysis.questions.insert(0, f"O sintoma pode ter relação com o serviço de {service.date:%d/%m/%Y}? "
                                         "Está coberto pela garantia?")
        analysis.history.append(note)


def analyze_problem(problem, today, usage=None):
    return analyze_symptom(problem.vehicle, problem.symptom, problem.description, problem.location, problem.severity,
                           today, exclude_pk=problem.pk, usage=usage)


USAGE_TIPS = {
    "urban_traffic": (("oil", "brakes_check"),
                      "Anda-e-para frequente pode ser considerado uso severo no manual; confira o plano para uso severo."),
    "short_trips": (("oil", "battery"),
                    "Trajetos curtos com motor frio podem se enquadrar como uso severo; confira no manual."),
    "highway": (("tires_check", "alignment"),
                "Velocidades maiores pedem pneus calibrados, alinhados e em bom estado."),
    "parked_days": (("battery",), "Carro parado vários dias descarrega a bateria; um teste de carga mostra o desgaste."),
    "frequent_load": (("tires_check", "suspension"),
                      "Carga frequente aumenta o desgaste de pneus e suspensão; calibre conforme a carga indicada."),
    "rough_roads": (("suspension", "alignment"),
                    "Buracos e ruas de terra desgastam suspensão e alinhamento mais rápido."),
    "dusty_roads": (("air_filter", "cabin_filter"), "Poeira satura os filtros de ar e de cabine mais rápido."),
}
TIME_SENSITIVE = ("brake_fluid", "coolant", "battery", "tires_check", "timing_belt")


@dataclass
class Tip:
    key: str
    title: str
    reason: str
    in_plan: bool
    kind_label: str


def usage_tips(profile, plan_keys):
    tips, seen = [], set()
    labels = dict(MaintenancePlan.Kind.choices)
    for flag in profile.active_flags if profile else []:
        keys, reason = USAGE_TIPS[flag]
        for key in keys:
            suggestion = SUGGESTIONS_BY_KEY[key]
            if key in seen:
                continue
            seen.add(key)
            tips.append(Tip(key, suggestion.title, reason, key in plan_keys, labels[suggestion.kind]))
    return tips


def review(vehicle, plans, profile, today):
    groups = {kind: [] for kind, _ in MaintenancePlan.Kind.choices}
    no_history = []
    for plan in plans:
        if not plan.is_open:
            continue
        if plan.due.state in ("overdue", "soon", "scheduled") or plan.kind == plan.Kind.DIAGNOSIS:
            groups[plan.kind].append(plan)
        elif plan.due.state in ("unknown", "needs_km"):
            no_history.append(plan)
    plan_keys = {plan.suggestion_key for plan in plans if plan.suggestion_key}
    time_sensitive = [SUGGESTIONS_BY_KEY[key] for key in TIME_SENSITIVE if key not in plan_keys]
    reading = vehicle.latest_reading
    problems = [(problem, analyze_problem(problem, today, profile))
                for problem in vehicle.problems.filter(status__in=Problem.ACTIVE_STATUSES)]
    problems.sort(key=lambda item: ["high", "medium", "low"].index(item[1].urgency))
    parts = [(service, part) for service in vehicle.services.filter(date__gte=today - timedelta(days=RELATED_WINDOW_DAYS))
             .prefetch_related("parts") for part in service.parts.all()]
    return {
        "groups": [(kind, label, groups[kind]) for kind, label in MaintenancePlan.Kind.choices],
        "attention_count": sum(len(items) for items in groups.values()), "no_history": no_history,
        "time_sensitive": time_sensitive, "tips": usage_tips(profile, plan_keys), "problems": problems,
        "parts": parts, "age": today.year - vehicle.model_year if vehicle.model_year <= today.year else 0,
        "km": fmt_km(reading.kilometers) if reading else None,
        "missing_suggestions": len(SUGGESTIONS_BY_KEY) - len(plan_keys),
        "plan_url": reverse("plan_list"),
    }
