# Register your models here.
from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Enveloppe


@admin.register(Enveloppe)
class EnveloppeAdmin(ModelAdmin):
    pass
