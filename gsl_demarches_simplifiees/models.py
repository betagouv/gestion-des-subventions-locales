# Create your models here.
from django.db import models


class DsModel(models.Model):
    created_at = models.DateTimeField("Date de création", auto_now_add=True)
    updated_at = models.DateTimeField("Date de modification", auto_now=True)

    class Meta:
        abstract = True


class Demarche(DsModel):
    """
    Class used to keep DS' "Démarches" data
    See:
    https://www.demarches-simplifiees.fr/graphql/schema/index.html#definition-Demarche
    https://www.demarches-simplifiees.fr/graphql/schema/index.html#definition-DemarcheDescriptor
    """

    STATE_BROUILLON = "brouillon"
    STATE_CLOSE = "close"
    STATE_DEPUBLIEE = "depubliee"
    STATE_PUBLIEE = "publiee"

    STATE_VALUES = (
        (STATE_BROUILLON, "Brouillon"),
        (STATE_CLOSE, "Close"),
        (STATE_DEPUBLIEE, "Dépubliée"),
        (STATE_PUBLIEE, "Publiée"),
    )

    # Fields prefixed with ds_ are DS fixed fields,
    # copied as-is, without any mapping needed.
    ds_id = models.CharField("Identifiant DS", unique=True)
    ds_number = models.IntegerField("Numéro DS", unique=True)  # type Int graphql
    ds_title = models.CharField("Titre DS")
    ds_state = models.CharField("État DS", choices=STATE_VALUES)
    ds_date_creation = models.DateTimeField(
        "Date de création dans DS", blank=True, null=True
    )
    ds_date_fermeture = models.DateTimeField(
        "Date de fermeture dans DS", blank=True, null=True
    )
    ds_instructeurs = models.ManyToManyField("gsl_demarches_simplifiees.Profile")

    class Meta:
        verbose_name = "Démarche"

    def __str__(self):
        return f"Démarche {self.ds_number}"


class Dossier(DsModel):
    """
    See https://www.demarches-simplifiees.fr/graphql/schema/index.html#definition-Dossier
    """

    STATE_ACCEPTE = "accepte"
    STATE_EN_CONSTRUCTION = "en_construction"
    STATE_EN_INSTRUCTION = "en_instruction"
    STATE_REFUSE = "refuse"
    STATE_SANS_SUITE = "sans_suite"

    DS_STATE_VALUES = (
        (STATE_ACCEPTE, "Accepté"),
        (STATE_EN_CONSTRUCTION, "En construction"),
        (STATE_EN_INSTRUCTION, "En instruction"),
        (STATE_REFUSE, "Refusé"),
        (STATE_SANS_SUITE, "Classé sans suite"),
    )

    ds_demarche = models.ForeignKey(Demarche, on_delete=models.CASCADE)
    ds_id = models.CharField("Identifiant DS")
    ds_number = models.IntegerField("Numéro DS")
    ds_state = models.CharField("État DS", choices=DS_STATE_VALUES)
    ds_date_depot = models.DateTimeField("Date de dépôt", null=True, blank=True)
    ds_date_passage_en_construction = models.DateTimeField(
        "Date de passage en construction", null=True, blank=True
    )
    ds_date_passage_en_instruction = models.DateTimeField(
        "Date de passage en instruction", null=True, blank=True
    )
    ds_date_derniere_modification_champs = models.DateTimeField(
        "Date de dernière modification", null=True, blank=True
    )

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
    porteur_de_projet_arrondissement = models.ForeignKey(
        "gsl_demarches_simplifiees.Arrondissement",
        models.SET_NULL,
        verbose_name="Département et arrondissement du porteur de projet",
        blank=True,
        null=True,
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
    projet_zonage = models.ManyToManyField(
        "gsl_demarches_simplifiees.ProjetZonage",
        verbose_name="Zonage spécifique : le projet est il situé dans l'une des zones suivantes ?",
    )
    projet_contractualisation = models.ManyToManyField(
        "gsl_demarches_simplifiees.ProjetContractualisation",
        verbose_name="Contractualisation : le projet est-il inscrit dans un ou plusieurs contrats avec l'Etat ?",
    )
    projet_contractualisation_autre = models.CharField(
        "Autre contrat : précisez le contrat concerné", blank=True
    )

    # ----
    environnement_transition_eco = models.BooleanField(
        "Le projet concourt-il aux enjeux de la transition écologique ?", null=True
    )
    environnement_objectifs = models.ManyToManyField(
        "gsl_demarches_simplifiees.ObjectifEnvironnemental",
        verbose_name="Si oui, indiquer quels sont les objectifs environnementaux impactés favorablement.",
    )
    environnement_artif_sols = models.BooleanField(
        "Le projet implique-t-il une artificialisation des sols ?", null=True
    )
    # ---
    date_debut = models.DateField(
        "Date de commencement de l'opération", null=True, blank=True
    )
    date_achevement = models.DateField(
        "Date prévisionnelle d'achèvement de l'opération", null=True
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
    demande_eligibilite_detr = models.ManyToManyField(
        "gsl_demarches_simplifiees.CritereEligibiliteDetr",
        verbose_name="Eligibilité de l'opération à la DETR",
    )

    demande_eligibilite_dsil = models.ManyToManyField(
        "gsl_demarches_simplifiees.CritereEligibiliteDsil",
        verbose_name="Eligibilité de l'opération à la DSIL",
    )
    demande_montant = models.DecimalField(
        "Montant de l'aide demandée", max_digits=12, decimal_places=2
    )
    demande_autres_aides = models.ManyToManyField(
        "gsl_demarches_simplifiees.AutreAide",
        verbose_name="En 2024, comptez-vous solliciter d'autres aides publiques pour financer cette opération  ?",
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

    MAPPED_FIELDS = (
        porteur_de_projet_nature,
        porteur_de_projet_arrondissement,
        porteur_de_projet_fonction,
        porteur_de_projet_nom,
        porteur_de_projet_prenom,
        maitrise_douvrage_deleguee,
        maitrise_douvrage_siret,
        projet_intitule,
        projet_adresse,
        projet_immo,
        projet_travaux,
        projet_zonage,
        projet_contractualisation,
        projet_contractualisation_autre,
        environnement_transition_eco,
        environnement_objectifs,
        environnement_artif_sols,
        date_debut,
        date_achevement,
        finance_cout_total,
        finance_recettes,
        demande_annee_precedente,
        demande_numero_demande_precedente,
        demande_dispositif_sollicite,
        demande_eligibilite_detr,
        demande_eligibilite_dsil,
        demande_montant,
        demande_autres_aides,
        demande_autre_precision,
        demande_autre_numero_dossier,
        demande_autre_dsil_detr,
        demande_priorite_dsil_detr,
    )

    class Meta:
        verbose_name = "Dossier"

    def __str__(self):
        return f"Dossier {self.ds_number}"


class DsChoiceLibelle(DsModel):
    label = models.CharField("Libellé", unique=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.label


class Arrondissement(DsChoiceLibelle):
    pass


class ProjetZonage(DsChoiceLibelle):
    pass


class ProjetContractualisation(DsChoiceLibelle):
    pass


class ObjectifEnvironnemental(DsChoiceLibelle):
    pass


class CritereEligibiliteDetr(DsChoiceLibelle):
    pass


class CritereEligibiliteDsil(DsChoiceLibelle):
    pass


class AutreAide(DsChoiceLibelle):
    pass


class Profile(DsModel):
    ds_id = models.CharField("Identifiant DS", unique=True)
    ds_email = models.EmailField("E-mail")

    def __str__(self):
        return f"Profil {self.ds_email}"


def mapping_field_choices():
    return tuple(
        (field.name, f"{field.name} - {field.verbose_name}")
        for field in Dossier.MAPPED_FIELDS
    )


def reversed_mapping():
    return


class FieldMappingForHuman(DsModel):
    label = models.CharField("Libellé du champ DS", unique=True)
    django_field = models.CharField(
        "Champ correspondant dans Django",
        choices=mapping_field_choices,
        blank=True,
    )
    demarche = models.ForeignKey(
        Demarche,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Démarche sur laquelle ce libellé de champ a été trouvé la première fois",
    )

    class Meta:
        verbose_name = "Réconciliation de champ"
        verbose_name_plural = "Réconciliations de champs"

    def __str__(self):
        return f"Réconciliation {self.pk}"


class FieldMappingForComputer(DsModel):
    demarche = models.ForeignKey(Demarche, on_delete=models.CASCADE)
    ds_field_id = models.CharField("ID du champ DS", unique=True)
    ds_field_label = models.CharField(
        "Libellé DS",
        help_text="Libellé au moment où ce champ a été rencontré pour la première fois — il a pu changer depuis !",
    )
    ds_field_type = models.CharField("Type de champ DS")
    django_field = models.CharField("Champ Django", choices=mapping_field_choices)
    field_mapping_for_human = models.ForeignKey(
        FieldMappingForHuman,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Réconciliation utilisée pour créer cette correspondance",
    )

    class Meta:
        verbose_name = "Correspondance technique"
        verbose_name_plural = "Correspondances techniques"

    def __str__(self):
        return f"Correspondance technique {self.pk}"
