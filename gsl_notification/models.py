from django.db import models


class ArreteSigne(models.Model):
    file = models.FileField(upload_to="arrete_signe/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

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
