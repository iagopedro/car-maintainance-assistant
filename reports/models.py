from django.conf import settings
from django.db import models


class BackupRecord(models.Model):
    class Source(models.TextChoices):
        WEB = "web", "Download pelo aplicativo"
        COMMAND = "command", "Comando agendado"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="backups")
    created_at = models.DateTimeField(auto_now_add=True)
    size = models.PositiveBigIntegerField()
    source = models.CharField(max_length=10, choices=Source.choices)

    class Meta:
        ordering = ["-created_at"]
