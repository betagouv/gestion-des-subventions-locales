from django.db import models

from gsl_core.models import Collegue


class ArreteSigne(models.Model):
    file = models.FileField(upload_to="arrete_signe/")
    uploaded_at = models.DateTimeField(auto_now_add=True)  # TODO rename created_at ??
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="arrete_signe",
    )

    def __str__(self):
        return f"Arrêté signé #{self.id} "

    @property
    def name(self):  # TODO test avec un / dans le nom ??
        return self.file.name.split("/")[-1]

    @property
    def type(self):  # TODO test avec un / dans le nom ??
        return self.file.name.split(".")[-1]

    @property
    def size(self):  # TODO test avec un / dans le nom ??
        return self.file.size
