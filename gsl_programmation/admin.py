from django.contrib import admin

from .models import Enveloppe, Scenario, SimulationProjet


@admin.register(Enveloppe)
class EnveloppeAdmin(admin.ModelAdmin):
    pass


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    pass


@admin.register(SimulationProjet)
class SimulationProjetAdmin(admin.ModelAdmin):
    list_display = ("__str__", "projet__dossier_ds__projet_intitule")
    search_fields = ("projet__dossier_ds__projet_intitule",)
