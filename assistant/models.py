from django.db import models

from garage.models import Vehicle


class UsageProfile(models.Model):
    vehicle = models.OneToOneField(Vehicle, on_delete=models.CASCADE, related_name="usage_profile")
    urban_traffic = models.BooleanField("Trânsito urbano com anda-e-para", default=False)
    short_trips = models.BooleanField("Trajetos curtos, com o motor ainda frio", default=False)
    highway = models.BooleanField("Viagens em rodovia", default=False)
    parked_days = models.BooleanField("Fica parado vários dias seguidos", default=False)
    frequent_load = models.BooleanField("Transporta carga ou equipamentos com frequência", default=False)
    rough_roads = models.BooleanField("Ruas esburacadas ou de terra", default=False)
    dusty_roads = models.BooleanField("Locais com muita poeira", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    FLAGS = ["urban_traffic", "short_trips", "highway", "parked_days", "frequent_load", "rough_roads", "dusty_roads"]

    @property
    def active_flags(self):
        return [name for name in self.FLAGS if getattr(self, name)]

    @property
    def labels(self):
        return [str(self._meta.get_field(name).verbose_name).lower() for name in self.active_flags]
