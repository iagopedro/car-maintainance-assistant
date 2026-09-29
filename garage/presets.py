import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)
ALLOWED_FIELDS = {"brand", "model", "version", "model_year", "manufacture_year", "engine", "fuel", "plate", "notes"}


def load_local_preset(name):
    try:
        data = json.loads(settings.LOCAL_PRESETS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable local presets file %s.", settings.LOCAL_PRESETS_FILE)
        return {}
    preset = data.get(name) if isinstance(data, dict) else None
    if not isinstance(preset, dict):
        return {}
    return {key: value for key, value in preset.items() if key in ALLOWED_FIELDS}
