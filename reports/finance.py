from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth, TruncYear
from django.utils.formats import date_format

from maintenance.models import Category, ServiceRecord
from planning.rules import add_months

ZERO = Decimal("0")
HORIZON_DAYS = 365
MIN_READING_SPAN_DAYS = 30


@dataclass(frozen=True)
class Bar:
    label: str
    total: Decimal
    count: int
    percent: int
    key: str = ""


def period_bounds(period, today):
    if period == "12m":
        return add_months(today.replace(day=1), -11), today
    if period.isdigit():
        year = int(period)
        return date(year, 1, 1), date(year, 12, 31)
    return None, None


def period_choices(vehicle, today):
    years = [str(day.year) for day in vehicle.services.exclude(date=None).dates("date", "year", order="DESC")]
    return [("12m", "Últimos 12 meses"), *[(year, year) for year in years if year], ("all", "Todo o período")]


def bars(rows, label_for, key_for=lambda row: ""):
    peak = max((row["total"] or ZERO for row in rows), default=ZERO)
    return [Bar(label_for(row), row["total"] or ZERO, row["count"],
                int((row["total"] or ZERO) * 100 / peak) if peak else 0, key_for(row)) for row in rows]


def monthly_bars(services, start, end):
    totals = {row["month"]: row for row in services.annotate(month=TruncMonth("date")).values("month")
              .annotate(total=Sum("total_cost"), count=Count("pk")).order_by("month")}
    rows, month = [], start.replace(day=1)
    while month <= end:
        found = totals.get(month, {})
        rows.append({"label": date_format(month, "M/y").capitalize(), "total": found.get("total"), "count": found.get("count", 0)})
        month = add_months(month, 1)
    return bars(rows, lambda row: row["label"])


def yearly_bars(services):
    rows = list(services.exclude(date=None).annotate(year=TruncYear("date")).values("year")
                .annotate(total=Sum("total_cost"), count=Count("pk")).order_by("year"))
    return bars(rows, lambda row: str(row["year"].year))


def km_per_day(vehicle, today):
    readings = list(vehicle.readings.filter(date__gte=today - timedelta(days=HORIZON_DAYS)).order_by("date", "pk"))
    if len(readings) < 2:
        readings = list(vehicle.readings.order_by("date", "pk"))
    if len(readings) < 2:
        return None
    first, last = readings[0], readings[-1]
    span = (last.date - first.date).days
    if span < MIN_READING_SPAN_DAYS or last.kilometers <= first.kilometers:
        return None
    return (last.kilometers - first.kilometers) / span


def projected_date(plan, rate, today):
    due = plan.due
    if due.state == "overdue":
        return today
    candidates = [day for day in (due.next_date, plan.scheduled_for) if day]
    if due.km_left is not None and rate:
        candidates.append(today + timedelta(days=int(due.km_left / rate)))
    return min(candidates) if candidates else None


def forecast(plans, rate, today):
    horizon = today + timedelta(days=HORIZON_DAYS)
    items, without_date = [], 0
    for plan in plans:
        if not plan.is_open:
            continue
        when = projected_date(plan, rate, today)
        if when is None:
            without_date += 1
        elif when <= horizon:
            items.append((when, plan))
    items.sort(key=lambda item: item[0])
    estimated = [plan.estimated_cost for _, plan in items if plan.estimated_cost is not None]
    return {
        "items": items, "total": sum(estimated, ZERO) if estimated else None,
        "missing_estimate": len(items) - len(estimated), "without_date": without_date,
    }


def cost_per_km(vehicle, total, today):
    readings = vehicle.readings.filter(date__gte=today - timedelta(days=HORIZON_DAYS)).order_by("date", "pk")
    first, last = readings.first(), readings.last()
    if not total or not first or first.pk == last.pk or last.kilometers <= first.kilometers:
        return None
    return (total / (last.kilometers - first.kilometers)).quantize(Decimal("0.01"))


def summarize(vehicle, plans, period, today):
    start, end = period_bounds(period, today)
    services = vehicle.services.all()
    if start:
        services = services.filter(date__gte=start, date__lte=end)
    totals = services.aggregate(total=Sum("total_cost"), count=Count("pk"),
                                unpriced=Count("pk", filter=Q(total_cost__isnull=True)),
                                parts=Sum("parts_cost"), labor=Sum("labor_cost"))
    total = totals["total"] or ZERO
    categories = dict(Category.choices)
    kinds = dict(ServiceRecord.Kind.choices)
    by_category = bars(list(services.values("category").annotate(total=Sum("total_cost"), count=Count("pk"))
                            .order_by("-total", "category")), lambda row: categories[row["category"]],
                       lambda row: row["category"])
    by_kind = bars(list(services.values("kind").annotate(total=Sum("total_cost"), count=Count("pk"))
                        .order_by("-total", "kind")), lambda row: kinds[row["kind"]], lambda row: row["kind"])
    if start:
        timeline = monthly_bars(services.exclude(date=None), start, end)
        months = today.month if period != "12m" and start <= today <= end else 12
        average = (total / months).quantize(Decimal("0.01")) if total else None
    else:
        timeline, average = yearly_bars(services), None
    rate = km_per_day(vehicle, today)
    return {
        "start": start, "end": end, "total": total, "count": totals["count"], "unpriced": totals["unpriced"],
        "parts": totals["parts"], "labor": totals["labor"], "by_category": by_category, "by_kind": by_kind,
        "timeline": timeline, "monthly_average": average, "undated": services.filter(date=None).count() if not start else 0,
        "all_time": vehicle.services.aggregate(total=Sum("total_cost"))["total"] or ZERO,
        "km_per_day": round(rate, 1) if rate else None, "forecast": forecast(plans, rate, today),
        "cost_per_km": cost_per_km(vehicle, total, today) if period == "12m" else None,
    }
