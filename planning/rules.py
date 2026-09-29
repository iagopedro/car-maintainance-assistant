import calendar
from dataclasses import dataclass
from datetime import date


def add_months(value, months):
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def fmt_km(value):
    return f"{value:,}".replace(",", ".")


def last_completion(services):
    known = [service for service in services if service.date or service.kilometers is not None]
    if not known:
        return None
    return max(known, key=lambda s: (s.date or date.min, s.kilometers if s.kilometers is not None else -1, s.pk))


STATES = {
    "overdue": (0, "Passou da referência"),
    "soon": (1, "Próximo"),
    "needs_km": (2, "Atualize o km"),
    "unknown": (3, "Sem referência"),
    "scheduled": (4, "Programado"),
    "ok": (5, "Em dia"),
    "done": (6, "Realizado"),
    "dismissed": (7, "Descartado"),
}


@dataclass(frozen=True)
class PlanDue:
    state: str
    next_km: int | None = None
    next_date: date | None = None
    km_left: int | None = None
    days_left: int | None = None
    last_service: object = None
    has_history: bool = False
    scheduled_for: date | None = None

    @property
    def order(self):
        return STATES[self.state][0]

    @property
    def label(self):
        return STATES[self.state][1]

    @property
    def target(self):
        parts = []
        if self.next_km is not None:
            parts.append(f"{fmt_km(self.next_km)} km")
        if self.next_date:
            parts.append(f"{self.next_date:%d/%m/%Y}")
        return " ou ".join(parts)

    @property
    def remaining(self):
        parts = []
        if self.km_left is not None:
            parts.append(f"faltam {fmt_km(self.km_left)} km" if self.km_left >= 0 else f"passou {fmt_km(-self.km_left)} km")
        if self.days_left is not None:
            days = abs(self.days_left)
            unit = "dia" if days == 1 else "dias"
            parts.append(f"faltam {days} {unit}" if self.days_left >= 0 else f"passou {days} {unit}")
        return ", ".join(parts)

    @property
    def summary(self):
        if self.state == "dismissed":
            return "Descartado"
        if self.state == "done":
            when = self.last_service.date if self.last_service and self.last_service.date else None
            return f"Realizado em {when:%d/%m/%Y}" if when else "Realizado"
        if self.state == "unknown":
            return "Realização registrada sem data ou km" if self.has_history else "Sem data ou km de referência"
        if self.state == "needs_km":
            return f"Previsto em {self.target}. Informe o km atual."
        prefix = f"Programado para {self.scheduled_for:%d/%m/%Y} · " if self.scheduled_for else ""
        text = f"{prefix}Próxima: {self.target}" if self.target else prefix.rstrip(" ·")
        return f"{text} · {self.remaining}" if self.remaining else text


def evaluate(plan, services, reading, today, km_ahead, days_ahead):
    last = last_completion(services)
    base = {"last_service": last, "has_history": bool(services),
            "scheduled_for": plan.scheduled_for if plan.status == plan.Status.SCHEDULED else None}
    if plan.status == plan.Status.DISMISSED:
        return PlanDue("dismissed", **base)
    if plan.status == plan.Status.DONE:
        return PlanDue("done", **base)
    next_km = plan.next_km
    if next_km is None and plan.interval_km and last and last.kilometers is not None:
        next_km = last.kilometers + plan.interval_km
    next_date = plan.next_date
    if next_date is None and plan.interval_months and last and last.date:
        next_date = add_months(last.date, plan.interval_months)
    km_left = next_km - reading.kilometers if next_km is not None and reading else None
    days_left = (next_date - today).days if next_date else None
    values = {**base, "next_km": next_km, "next_date": next_date, "km_left": km_left, "days_left": days_left}
    if (km_left is not None and km_left < 0) or (days_left is not None and days_left < 0):
        return PlanDue("overdue", **values)
    if base["scheduled_for"]:
        return PlanDue("scheduled", **values)
    if (km_left is not None and km_left <= km_ahead) or (days_left is not None and days_left <= days_ahead):
        return PlanDue("soon", **values)
    if next_km is None and next_date is None:
        return PlanDue("unknown", **values)
    if next_km is not None and km_left is None and next_date is None:
        return PlanDue("needs_km", **values)
    return PlanDue("ok", **values)
