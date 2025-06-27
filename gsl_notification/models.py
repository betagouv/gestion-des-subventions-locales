from django.db import models

from gsl_core.models import Collegue


class ArreteSigne(models.Model):
    file = models.FileField(upload_to="arrete_signe/")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="arrete_signe",
    )

    class Meta:
        verbose_name = "Arrêté signé"
        verbose_name_plural = "Arrêtés signés"

    def __str__(self):
        return f"Arrêté signé #{self.id} "

    @property
    def name(self):
        return self.file.name.split("/")[-1]

    @property
    def type(self):
        return self.file.name.split(".")[-1]

    @property
    def size(self):
        return self.file.size
