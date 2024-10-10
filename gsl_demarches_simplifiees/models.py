# Create your models here.
from django.db import models


class Demarche(models.Model):
    """
    Class used to keep DS' "Démarches" data
    See:
    https://www.demarches-simplifiees.fr/graphql/schema/index.html#definition-Demarche
    https://www.demarches-simplifiees.fr/graphql/schema/index.html#definition-DemarcheDescriptor
    """

    STATE_VALUES = (
        ("brouillon", "Brouillon"),
        ("close", "Close"),
        ("depubliee", "Dépubliée"),
        ("publiee", "Publiée"),
    )

    # Fields prefixed with ds_ are DS fixed fields,
    # copied as-is, without any mapping needed.
    ds_id = models.CharField("Identifiant DS")
    ds_number = models.IntegerField("Numéro DS")  # type Int graphql
    ds_title = models.CharField("Titre DS")
    ds_state = models.CharField("État DS", choices=STATE_VALUES)
    ds_date_creation = models.DateTimeField(
        "Date de création dans DS"
    )  # ISO8601DateTime
    ds_date_fermeture = models.DateTimeField(
        "Date de fermeture dans DS", blank=True
    )  # ISO8601DateTime
    ds_instructeurs = models.ManyToManyField("gsl_demarches_simplifiees.Profile")

    class Meta:
        verbose_name = "Démarche"

    def __str__(self):
        return f"Démarche {self.ds_number}"


class Dossier(models.Model):
    """
    See https://www.demarches-simplifiees.fr/graphql/schema/index.html#definition-Dossier
    """

    DS_STATE_VALUES = (
        ("accepte", "Accepté"),
        ("en_construction", "En construction"),
        ("en_instruction", "En instruction"),
        ("refuse", "Refusé"),
        ("sans_suite", "Classé sans suite"),
    )
    ds_demarche = models.ForeignKey(Demarche, on_delete=models.CASCADE)
    ds_id = models.CharField("Identifiant DS")
    ds_number = models.IntegerField("Numéro DS")
    ds_state = models.CharField("État DS", choices=DS_STATE_VALUES)
    ds_date = models.DateTimeField("Date de dépôt")  # @todo

    collectivite = models.CharField("Collectivité", blank=True)
    intitule = models.CharField("Intitulé", blank=True)
    montant_demande = models.IntegerField("Montant demandé", null=True, blank=True)
    cout_total_projet = models.IntegerField(
        "Coût total du projet", null=True, blank=True
    )

    MAPPED_FIELDS = (
        collectivite,
        intitule,
        montant_demande,
        cout_total_projet,
    )

    class Meta:
        verbose_name = "Dossier"

    def __str__(self):
        return f"Dossier {self.ds_number}"


class Profile(models.Model):
    ds_id = models.CharField("Identifiant DS")
    ds_email = models.EmailField("E-mail")

    def __str__(self):
        return f"Profil {self.ds_email}"


def mapping_field_choices():
    return [(field.name, field.verbose_name) for field in Dossier.MAPPED_FIELDS]


class FieldMappingForHuman(models.Model):
    label = models.CharField("Libellé du champ DS")
    django_field = models.CharField(
        "Champ correspondant dans Django", choices=mapping_field_choices
    )

    def __str__(self):
        return f"Correspondance {self.pk}"


class FieldMappingForComputer(models.Model):
    def __str__(self):
        return f"Correspondance technique {self.pk}"
