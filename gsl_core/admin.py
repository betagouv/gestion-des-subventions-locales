from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from gsl_core.models import Collegue

admin.site.register(Collegue, UserAdmin)

admin.site.unregister(Group)
