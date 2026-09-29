from decimal import Decimal

from django import template

register = template.Library()

CATEGORY_ICONS = {
    "oil": "droplet", "filters": "filter", "brakes": "disc", "tires": "circle-dot", "suspension": "move-vertical",
    "cooling": "thermometer", "battery": "battery", "electrical": "zap", "engine": "cog", "transmission": "settings-2",
    "fuel": "fuel", "belts": "repeat", "ac": "snowflake", "audio": "speaker", "body": "car-front",
    "general": "clipboard-check", "other": "wrench",
}
SYMPTOM_ICONS = {
    "noise": "volume-2", "vibration": "activity", "warning_light": "triangle-alert", "starting": "key-round",
    "consumption": "fuel", "malfunction": "circle-alert", "leak": "droplets", "electrical": "zap",
    "wear": "search", "other": "message-circle",
}


@register.filter
def brl(value):
    if value is None or value == "":
        return "Sem valor"
    amount = f"{Decimal(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {amount}"


@register.filter
def category_icon(value):
    return CATEGORY_ICONS.get(value, "wrench")


@register.filter
def symptom_icon(value):
    return SYMPTOM_ICONS.get(value, "message-circle")
