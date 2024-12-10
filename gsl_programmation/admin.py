from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Enveloppe, Scenario, SimulationProjet


@admin.register(Enveloppe)
class EnveloppeAdmin(ModelAdmin):
    pass


class SimulationProjetInline(TabularInline):
    model = SimulationProjet
    fields = ("projet", "enveloppe", "montant", "taux", "status")


@admin.register(Scenario)
class ScenarioAdmin(ModelAdmin):
    pass
