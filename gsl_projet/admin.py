from django.contrib import admin

from .models import Demandeur, Projet


@admin.register(Demandeur)
class DemandeurAdmin(admin.ModelAdmin):
    pass


@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    pass
