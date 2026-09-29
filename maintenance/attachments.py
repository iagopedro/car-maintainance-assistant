from pathlib import Path

from django import forms
from django.core.exceptions import SuspiciousFileOperation
from django.utils.text import get_valid_filename

from .models import Attachment

EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES = 10


def detect_content_type(upload):
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "image/heic"
    return None


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class AttachmentField(forms.FileField):
    widget = MultipleFileInput

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", "Fotos e documentos")
        kwargs.setdefault("help_text", "Nota fiscal, orçamento ou fotos. JPG, PNG, WEBP, HEIC ou PDF, até 10 MB cada.")
        super().__init__(**kwargs)
        self.widget.attrs["accept"] = "image/*,application/pdf"

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        if len(files) > MAX_FILES:
            raise forms.ValidationError(f"Envie até {MAX_FILES} arquivos por vez.")
        errors = []
        for upload in files:
            upload = super().clean(upload, initial)
            if upload.size > MAX_FILE_SIZE:
                errors.append(f"{upload.name}: arquivo maior que 10 MB.")
                continue
            upload.detected_type = detect_content_type(upload)
            if not upload.detected_type:
                errors.append(f"{upload.name}: formato não aceito.")
        if errors:
            raise forms.ValidationError(errors)
        return list(files)


def safe_display_name(name, extension):
    try:
        cleaned = get_valid_filename(Path(name).name)
    except SuspiciousFileOperation:
        cleaned = ""
    return (cleaned or f"anexo{extension}")[:200]


def save_attachments(files, *, service=None, problem=None):
    saved = []
    try:
        for upload in files:
            extension = EXTENSIONS[upload.detected_type]
            attachment = Attachment(service=service, problem=problem, content_type=upload.detected_type,
                                    size=upload.size, original_name=safe_display_name(upload.name, extension))
            attachment.file.save(f"upload{extension}", upload, save=False)
            saved.append(attachment.file)
            attachment.save()
    except Exception:
        for stored in saved:
            stored.storage.delete(stored.name)
        raise
    return len(saved)
