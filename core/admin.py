from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from core.models import Collegue

admin.site.register(Collegue, UserAdmin)
