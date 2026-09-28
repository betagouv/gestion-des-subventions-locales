from typing import TYPE_CHECKING

from django.db import models

from gsl.core.models import BaseModel, Collegue

from .projet import Projet

if TYPE_CHECKING:
    pass


class ProjetNote(BaseModel):
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=100)
    content = models.TextField()
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
