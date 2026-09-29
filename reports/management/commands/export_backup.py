import shutil
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reports.backup import create_backup
from reports.models import BackupRecord


class Command(BaseCommand):
    help = "Gera um backup .zip (dados e anexos) de um usuário, restaurável pela página Seus dados."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--output", default="backups", help="Pasta de destino (padrão: backups).")

    def handle(self, *args, username, output, **options):
        user = get_user_model().objects.filter(username=username).first()
        if not user:
            raise CommandError(f"Usuário '{username}' não encontrado.")
        folder = Path(output)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"rodagem-backup-{username}-{timezone.localtime():%Y-%m-%d-%H%M%S}.zip"
        handle, size, missing = create_backup(user)
        with handle, target.open("xb") as destination:
            shutil.copyfileobj(handle, destination)
        BackupRecord.objects.create(owner=user, size=size, source=BackupRecord.Source.COMMAND)
        if missing:
            self.stderr.write(f"{missing} anexo(s) não encontrados no disco ficaram fora do backup.")
        self.stdout.write(self.style.SUCCESS(f"Backup salvo em {target} ({size} bytes)."))
