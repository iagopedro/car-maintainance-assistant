import hashlib
import json
import re
import tempfile
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from garage.models import OdometerReading, Vehicle
from maintenance.attachments import EXTENSIONS, MAX_FILE_SIZE, detect_content_type, safe_display_name
from maintenance.models import Attachment, Problem, ProblemUpdate, ServicePart, ServiceRecord
from planning.models import AlertPreferences, MaintenancePlan

FORMAT, VERSION = "rodagem-backup", 1
ATTACHMENT_NAME = re.compile(r"^attachments/[0-9a-f]{32}\.(jpg|png|webp|heic|pdf)$")
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_JSON_BYTES = 50 * 1024 * 1024

# (section, model, fields, foreign keys -> section, owner lookup). Order matters for restore.
SECTIONS = [
    ("vehicles", Vehicle, ["brand", "model", "version", "manufacture_year", "model_year", "engine", "engine_verified",
                           "fuel", "acquisition_date", "plate", "notes"], {}, "owner"),
    ("readings", OdometerReading, ["date", "kilometers", "source", "notes"], {"vehicle": "vehicles"}, "vehicle__owner"),
    ("plans", MaintenancePlan, ["title", "category", "kind", "priority", "reason", "interval_km", "interval_months",
                                "next_km", "next_date", "status", "scheduled_for", "dismissed_reason", "estimated_cost",
                                "source", "source_verified", "suggestion_key", "notes"],
     {"vehicle": "vehicles"}, "vehicle__owner"),
    ("services", ServiceRecord, ["category", "title", "date", "kilometers", "kind", "workshop", "description",
                                 "parts_cost", "labor_cost", "total_cost", "warranty_until", "warranty_notes", "notes"],
     {"vehicle": "vehicles", "plan": "plans", "odometer_reading": "readings"}, "vehicle__owner"),
    ("parts", ServicePart, ["name", "brand_model"], {"service": "services"}, "service__vehicle__owner"),
    ("problems", Problem, ["symptom", "title", "description", "reported_on", "kilometers", "location", "category",
                           "severity", "status", "diagnosis", "ruled_out", "solution", "resolved_on"],
     {"vehicle": "vehicles", "resolved_by_service": "services"}, "vehicle__owner"),
    ("problem_updates", ProblemUpdate, ["date", "status", "note"], {"problem": "problems"}, "problem__vehicle__owner"),
]
ORDERING = {"readings": ["date", "pk"]}
PREFERENCE_FIELDS = ["km_ahead", "days_ahead", "reading_reminder_days", "show_high", "show_medium", "show_low"]


class BackupError(Exception):
    pass


def dump(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def serialize(obj, fields, foreign_keys):
    row = {"id": obj.pk, **{name: dump(getattr(obj, name)) for name in fields}}
    row.update({f"{name}_id": getattr(obj, f"{name}_id") for name in foreign_keys})
    if hasattr(obj, "created_at"):
        row["created_at"] = dump(obj.created_at)
    return row


def owned_attachments(user):
    return Attachment.objects.filter(Q(service__vehicle__owner=user) | Q(problem__vehicle__owner=user)).order_by("pk")


def create_backup(user):
    """Write the owner's data and attachments to a temporary zip; returns (file, size, missing attachments)."""
    data, counts = {}, {}
    for section, model, fields, foreign_keys, owner_lookup in SECTIONS:
        queryset = model.objects.filter(**{owner_lookup: user}).order_by(*ORDERING.get(section, ["pk"]))
        data[section] = [serialize(obj, fields, foreign_keys) for obj in queryset]
        counts[section] = len(data[section])
    prefs = AlertPreferences.for_user(user)
    data["alert_preferences"] = {name: getattr(prefs, name) for name in PREFERENCE_FIELDS}
    handle = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    missing = 0
    with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
        data["attachments"] = []
        for attachment in owned_attachments(user):
            try:
                with attachment.file.open("rb") as source:
                    content = source.read()
            except FileNotFoundError:
                missing += 1
                continue
            name = f"attachments/{uuid.uuid4().hex}{EXTENSIONS[attachment.content_type]}"
            archive.writestr(name, content)
            data["attachments"].append({
                "id": attachment.pk, "service_id": attachment.service_id, "problem_id": attachment.problem_id,
                "file": name, "sha256": hashlib.sha256(content).hexdigest(), "original_name": attachment.original_name,
                "content_type": attachment.content_type,
            })
        counts["attachments"] = len(data["attachments"])
        manifest = {"format": FORMAT, "version": VERSION, "created_at": timezone.now().isoformat(),
                    "counts": counts, "missing_attachments": missing}
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False))
    size = handle.tell()
    handle.seek(0)
    return handle, size, missing


def read_limited(archive, info, limit):
    if info.file_size > limit:
        raise BackupError(f"O item {info.filename} do backup é grande demais.")
    with archive.open(info) as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise BackupError(f"O item {info.filename} do backup é grande demais.")
    return content


def load_json(archive, infos, name):
    if name not in infos:
        raise BackupError(f"O backup não contém {name}.")
    try:
        return json.loads(read_limited(archive, infos[name], MAX_JSON_BYTES).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError(f"{name} está corrompido.") from error


def restore_rows(user, data):
    maps = {}
    for section, model, fields, foreign_keys, _ in SECTIONS:
        rows = data.get(section, [])
        if not isinstance(rows, list):
            raise BackupError("Estrutura de dados inválida.")
        maps[section] = {}
        for row in rows:
            values = {name: model._meta.get_field(name).to_python(row[name]) for name in fields}
            for name, target in foreign_keys.items():
                reference = row.get(f"{name}_id")
                values[name] = maps[target][reference] if reference is not None else None
            if section == "vehicles":
                values["owner"] = user
            obj = model(**values)
            obj.full_clean()
            obj.save()
            created_at = parse_datetime(row.get("created_at") or "")
            if created_at:
                model.objects.filter(pk=obj.pk).update(created_at=created_at)
            maps[section][row["id"]] = obj
    return maps


def restore_attachments(archive, infos, rows, maps, saved):
    for row in rows:
        name = row["file"]
        if not ATTACHMENT_NAME.match(name) or name not in infos:
            raise BackupError("Um anexo listado não está no arquivo de backup.")
        content = read_limited(archive, infos[name], MAX_FILE_SIZE)
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise BackupError("Um anexo do backup está corrompido.")
        detected = detect_content_type(ContentFile(content))
        if detected is None or detected != row["content_type"]:
            raise BackupError("Um anexo do backup tem formato inválido.")
        if row.get("service_id") is not None:
            target = {"service": maps["services"][row["service_id"]]}
        else:
            target = {"problem": maps["problems"][row["problem_id"]]}
        extension = EXTENSIONS[detected]
        attachment = Attachment(**target, content_type=detected, size=len(content),
                                original_name=safe_display_name(str(row.get("original_name", "")), extension))
        attachment.file.save(f"upload{extension}", ContentFile(content), save=False)
        saved.append(attachment.file)
        attachment.full_clean()
        attachment.save()


def restore_preferences(user, values):
    prefs = AlertPreferences.for_user(user)
    for name in PREFERENCE_FIELDS:
        if name in values:
            setattr(prefs, name, AlertPreferences._meta.get_field(name).to_python(values[name]))
    prefs.full_clean()
    prefs.save()


def restore_backup(user, upload):
    if Vehicle.objects.filter(owner=user).exists():
        raise BackupError("A restauração só é permitida em uma conta sem veículos, para não misturar dados.")
    if upload.size > MAX_UPLOAD_BYTES:
        raise BackupError("O arquivo é maior que o limite de 500 MB.")
    try:
        archive = zipfile.ZipFile(upload)
    except zipfile.BadZipFile as error:
        raise BackupError("O arquivo não é um backup válido (.zip).") from error
    saved = []
    with archive:
        infos = {info.filename: info for info in archive.infolist()}
        for name, info in infos.items():
            if info.is_dir() or not (name in ("manifest.json", "data.json") or ATTACHMENT_NAME.match(name)):
                raise BackupError("O arquivo contém itens inesperados e não parece um backup do Rodagem.")
        if sum(info.file_size for info in infos.values()) > MAX_UNCOMPRESSED_BYTES:
            raise BackupError("O conteúdo do backup é grande demais.")
        manifest = load_json(archive, infos, "manifest.json")
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise BackupError("O arquivo não é um backup do Rodagem.")
        if manifest.get("version") != VERSION:
            raise BackupError("Versão de backup não suportada por esta versão do aplicativo.")
        data = load_json(archive, infos, "data.json")
        if not isinstance(data, dict):
            raise BackupError("Estrutura de dados inválida.")
        try:
            with transaction.atomic():
                maps = restore_rows(user, data)
                restore_attachments(archive, infos, data.get("attachments", []), maps, saved)
                restore_preferences(user, data.get("alert_preferences") or {})
        except BackupError:
            cleanup(saved)
            raise
        except (ValidationError, IntegrityError, KeyError, TypeError, ValueError, AttributeError) as error:
            cleanup(saved)
            raise BackupError("Os dados do backup são inválidos ou incompatíveis. Nada foi importado.") from error
        except Exception:
            cleanup(saved)
            raise
    return {section: len(mapping) for section, mapping in maps.items()} | {"attachments": len(saved)}


def cleanup(files):
    for stored in files:
        stored.storage.delete(stored.name)
