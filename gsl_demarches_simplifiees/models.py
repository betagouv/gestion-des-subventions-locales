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

    NATURE_PORTEUR_DE_PROJET_VALUES = (
        ("commune", "Commune"),
        ("epci", "EPCI"),
        ("petr", "Pôle d'équilibre territorial et rural"),
        ("syco", "Syndicat de communes"),
    )
    porteur_de_projet_nature = models.CharField(
        "Nature du porteur de projet",
        blank=True,
        choices=NATURE_PORTEUR_DE_PROJET_VALUES,
    )
    # @todo: foreignkey vers un modèle "arrondissement"
    porteur_de_projet_arrondissement = models.CharField(
        "Département et arrondissement du porteur de projet", blank=True
    )
    porteur_de_projet_fonction = models.CharField(
        "Fonction du porteur de projet", blank=True
    )
    porteur_de_projet_nom = models.CharField("Nom du porteur de projet", blank=True)
    porteur_de_projet_prenom = models.CharField(
        "Prénom du porteur de projet", blank=True
    )
    # ---
    maitrise_douvrage_deleguee = models.BooleanField(
        "La maîtrise d'ouvrage de l'opération sera-t-elle déléguée ?", null=True
    )
    maitrise_douvrage_siret = models.CharField(
        "Identification du maître d'ouvrage", blank=True
    )
    # ---
    projet_intitule = models.CharField("Intitulé du projet", blank=True)
    projet_adresse = models.TextField(
        "Adresse principale du projet", blank=True
    )  # @todo : addresse = complexe
    projet_immo = models.BooleanField(
        "Le projet d'investissement comprend-il des acquisitions immobilières ?",
        null=True,
    )
    projet_travaux = models.BooleanField(
        "Le projet d'investissement comprend-il des travaux ?", null=True
    )
    # @todo: M2M modèle ProjetZonage
    projet_zonage = models.CharField(
        "Zonage spécifique : le projet est il situé dans l'une des zones suivantes ?",
        blank=True,
    )
    # @todo: M2M modèle ProjetContractualisation
    projet_contractualisation = models.CharField(
        "Contractualisation : le projet est-il inscrit dans un ou plusieurs contrats avec l'Etat ?",
        blank=True,
    )
    projet_contractualisation_autre = models.CharField(
        "Autre contrat : précisez le contrat concerné", blank=True
    )
    # ----
    environnement_transition_eco = models.BooleanField(
        "Le projet concourt-il aux enjeux de la transition écologique ?"
    )
    # @todo M2M modèle objectifs environnementaux
    environnement_objectifs = models.CharField(
        "Si oui, indiquer quels sont les objectifs environnementaux impactés favorablement."
    )
    environnement_artif_sols = models.BooleanField(
        "Le projet implique-t-il une artificialisation des sols ?", null=True
    )
    # ---
    date_debut = models.DateField(
        "Date de commencement de l'opération", null=True, blank=True
    )
    date_achevement = models.DateField(
        "Date prévisionnelle d'achèvement de l'opération"
    )
    # ---
    finance_cout_total = models.DecimalField(
        "Coût total de l'opération (en euros HT)", max_digits=12, decimal_places=2
    )
    finance_recettes = models.BooleanField("Le projet va-t-il générer des recettes ?")
    # ---
    demande_annee_precedente = models.BooleanField(
        "Avez-vous déjà présenté cette opération au titre de campagnes DETR/DSIL en 2023 ?"
    )
    demande_numero_demande_precedente = models.CharField(
        "Précisez le numéro du dossier déposé antérieurement"
    )
    DEMANDE_DISPOSITIF_SOLLICITE_VALUES = (
        ("DETR", "DETR"),
        ("DSIL", "DSIL"),
    )
    demande_dispositif_sollicite = models.CharField(
        "Dispositif de financement sollicité",
        choices=DEMANDE_DISPOSITIF_SOLLICITE_VALUES,
    )
    # @todo M2M
    demande_eligibilite_detr = models.CharField("Eligibilité de l'opération à la DETR")
    # @todo M2M
    demande_eligibilite_dsil = models.CharField("Eligibilité de l'opération à la DSIL")
    demande_montant = models.DecimalField(
        "Montant de l'aide demandée", max_digits=12, decimal_places=2
    )
    # @todo M2M
    demande_autres_aides = models.CharField(
        "En 2024, comptez-vous solliciter d'autres aides publiques pour financer cette opération  ?"
    )
    demande_autre_precision = models.TextField(
        "Autre - précisez le dispositif de financement concerné"
    )
    demande_autre_numero_dossier = models.CharField(
        "Si votre dossier a déjà été déposé, précisez le numéro de dossier"
    )
    demande_autre_dsil_detr = models.BooleanField(
        "Présentez-vous une autre opération au titre de la DETR/DSIL 2024 ?"
    )
    demande_priorite_dsil_detr = models.IntegerField(
        "Si oui, précisez le niveau de priorité de ce dossier."
    )

    MAPPED_FIELDS = ()

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
