from logging import getLogger

from django.db import models
from django.urls import reverse
from django.utils import timezone

from gsl_core.models import Adresse, Collegue, Perimetre
from gsl_core.models import Arrondissement as CoreArrondissement
from gsl_core.models import Departement as CoreDepartement
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    MIN_DEMANDE_MONTANT_FOR_AVIS_DETR,
)

logger = getLogger(__name__)


class TimestampedModel(models.Model):
    created_at = models.DateTimeField("Date de création", auto_now_add=True)
    updated_at = models.DateTimeField("Date de modification", auto_now=True)

    class Meta:
        abstract = True


class Demarche(TimestampedModel):
    """
    Class used to keep DN' "Démarches" data
    See:
    https://www.demarches-simplifiees.fr/graphql/schema/types/Demarche
    https://www.demarches-simplifiees.fr/graphql/schema/types/DemarcheDescriptor
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

    # Fields prefixed with ds_ are DN fixed fields,
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

    raw_ds_data = models.JSONField("Données DS brutes", null=True, blank=True)
    active_revision_id = models.CharField(
        "Identifiant de la révision DS active", blank=True, default=""
    )
    active_revision_date = models.DateTimeField(
        "Date de publication de la révision active", blank=True, null=True
    )
    updated_since = models.DateTimeField(
        "Date de dernière mise à jour des dossiers", blank=True, null=True
    )

    class Meta:
        verbose_name = "Démarche"

    def __str__(self):
        return f"Démarche {self.ds_number} - {self.ds_title}"

    @property
    def json_url(self):
        return reverse(
            "ds:view-demarche-json", kwargs={"demarche_ds_number": self.ds_number}
        )


class FormeJuridique(models.Model):
    code = models.CharField("Code", primary_key=True)
    libelle = models.CharField("Libellé")

    class Meta:
        verbose_name = "Forme Juridique"
        verbose_name_plural = "Formes Juridiques"

    def __str__(self):
        return f"{self.code} — {self.libelle}"


class Naf(models.Model):
    code = models.CharField("Code", primary_key=True)
    libelle = models.CharField("Libellé")

    class Meta:
        verbose_name = "Code NAF"
        verbose_name_plural = "Codes NAF"

    def __str__(self):
        return f"{self.code} — {self.libelle}"


class PersonneMorale(models.Model):
    """
    see https://www.demarches-simplifiees.fr/graphql/schema/types/PersonneMorale
    """

    siret = models.CharField("SIRET", unique=True, primary_key=True)
    raison_sociale = models.CharField("Raison Sociale", blank=True)
    address = models.ForeignKey(
        Adresse,
        on_delete=models.PROTECT,
        verbose_name="Adresse",
        null=True,
        blank=True,
    )

    siren = models.CharField("SIREN", blank=True)
    naf = models.ForeignKey(Naf, on_delete=models.PROTECT, null=True)
    forme_juridique = models.ForeignKey(
        FormeJuridique, on_delete=models.PROTECT, null=True
    )

    class Meta:
        verbose_name = "Personne morale"
        verbose_name_plural = "Personnes morales"

    def __str__(self):
        return self.raison_sociale or self.siret

    def update_from_raw_ds_data(self, ds_data):
        self.siret = ds_data.get("siret")
        self.naf, _ = Naf.objects.get_or_create(
            code=ds_data.get("naf"), defaults={"libelle": ds_data.get("libelleNaf")}
        )

        adresse = self.address or Adresse()
        adresse.update_from_raw_ds_data(ds_data.get("address"))
        adresse.save()
        self.address = adresse

        entreprise_data = ds_data.get("entreprise")
        if entreprise_data:
            self.raison_sociale = entreprise_data.get("raisonSociale")
            self.forme_juridique, _ = FormeJuridique.objects.get_or_create(
                code=entreprise_data.get("formeJuridiqueCode"),
                defaults={"libelle": entreprise_data.get("formeJuridique")},
            )

        return self


class DossierData(TimestampedModel):
    """
    See https://www.demarches-simplifiees.fr/graphql/schema/types/Dossier
    """

    ds_demarche = models.ForeignKey(Demarche, on_delete=models.CASCADE)
    raw_data = models.JSONField("Données DS brutes", null=True, blank=True)

    class Meta:
        verbose_name = "Données de dossier DN"
        verbose_name_plural = "Données de dossiers DN"

    def __str__(self):
        if "number" in self.raw_data:
            return f"Données de dossier #{self.raw_data['number']}"
        return "Données de dossier (vide)"


class DossierQuerySet(models.QuerySet):
    def for_user(self, user: Collegue):
        if user.perimetre is None:
            if user.is_staff or user.is_superuser:
                return self
            return self.none()

        return self.for_perimetre(user.perimetre)

    def for_perimetre(self, perimetre: Perimetre | None):
        if perimetre is None:
            return self
        if perimetre.arrondissement:
            return self.filter(
                projet__perimetre__arrondissement=perimetre.arrondissement
            )
        if perimetre.departement:
            return self.filter(projet__perimetre__departement=perimetre.departement)
        if perimetre.region:
            return self.filter(projet__perimetre__region=perimetre.region)

    def sans_pieces(self):
        return self.filter(demande_renouvellement__contains="SANS")


class Dossier(TimestampedModel):
    """
    See https://www.demarches-simplifiees.fr/graphql/schema/types/Dossier
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

    ds_data = models.OneToOneField(DossierData, on_delete=models.CASCADE)
    ds_id = models.CharField("Identifiant DS")
    ds_number = models.IntegerField("Numéro DS", unique=True)
    ds_demarche_number = models.IntegerField("Numéro de la démarche")
    ds_state = models.CharField("État DS", choices=DS_STATE_VALUES)
    ds_date_depot = models.DateTimeField("Date de dépôt", null=True, blank=True)
    ds_date_passage_en_construction = models.DateTimeField(
        "Date de passage en construction", null=True, blank=True
    )
    ds_date_passage_en_instruction = models.DateTimeField(
        "Date de passage en instruction", null=True, blank=True
    )
    ds_date_derniere_modification = models.DateTimeField(
        "Date de dernière modification", null=True, blank=True
    )
    ds_date_derniere_modification_champs = models.DateTimeField(
        "Date de dernière modification des champs", null=True, blank=True
    )
    ds_date_traitement = models.DateTimeField(
        "Date de traitement",
        null=True,
        blank=True,
        help_text=(
            "Date de passage à l’état « Accepté », « Refusé » ou "
            "« Classé sans suite », le cas échéant."
        ),
    )
    ds_demandeur = models.ForeignKey(
        PersonneMorale, on_delete=models.PROTECT, verbose_name="Demandeur", null=True
    )
    ds_instructeurs = models.ManyToManyField("gsl_demarches_simplifiees.Profile")

    porteur_de_projet_nature = models.ForeignKey(
        "gsl_demarches_simplifiees.NaturePorteurProjet",
        models.SET_NULL,
        verbose_name="Nature du porteur de projet",
        blank=True,
        null=True,
    )
    porteur_de_projet_departement = models.ForeignKey(
        "gsl_demarches_simplifiees.Departement",
        models.SET_NULL,
        verbose_name="Département ou collectivité du demandeur",
        blank=True,
        null=True,
    )
    porteur_de_projet_arrondissement = models.ForeignKey(
        "gsl_demarches_simplifiees.Arrondissement",
        models.SET_NULL,
        verbose_name="Arrondissement du demandeur",
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
    projet_adresse = models.ForeignKey(
        Adresse,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name="Adresse principale du projet",
    )
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
        blank=True,
    )
    projet_zonage_autre = models.CharField(
        "Autre zonage : précisez le nom du zonage", blank=True
    )
    projet_contractualisation = models.ManyToManyField(
        "gsl_demarches_simplifiees.ProjetContractualisation",
        verbose_name="Contractualisation : le projet est-il inscrit dans un ou plusieurs contrats avec l'Etat ?",
        blank=True,
    )
    projet_contractualisation_autre = models.CharField(
        "Autre contrat : précisez le nom du contrat", blank=True
    )

    # ----
    environnement_transition_eco = models.BooleanField(
        "Le projet concourt-il aux enjeux de la transition écologique ?", null=True
    )
    environnement_objectifs = models.ManyToManyField(
        "gsl_demarches_simplifiees.ObjectifEnvironnemental",
        verbose_name="Si oui, indiquer quels sont les objectifs environnementaux impactés favorablement.",
        blank=True,
    )
    environnement_artif_sols = models.BooleanField(
        "Le projet implique-t-il une artificialisation des sols ?", null=True
    )
    # ---
    date_debut = models.DateField(
        "Date de commencement de l'opération", null=True, blank=True
    )
    date_achevement = models.DateField(
        "Date prévisionnelle d'achèvement de l'opération", null=True, blank=True
    )
    # ---
    finance_cout_total = models.DecimalField(
        "Coût total de l'opération (en euros HT)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    finance_recettes = models.BooleanField(
        "Le projet va-t-il générer des recettes ?", null=True
    )
    # ---
    demande_renouvellement = models.CharField(
        "Souhaitez-vous effectuer une nouvelle demande ou renouveler une demande précédente ?",
        blank=True,
    )
    demande_numero_demande_precedente = models.CharField(
        "Précisez le numéro du dossier déposé antérieurement",
        blank=True,
    )

    demande_dispositif_sollicite = models.CharField(
        "Dispositif de financement sollicité",
        blank=True,
    )
    demande_categorie_dsil = models.ForeignKey(
        "gsl_demarches_simplifiees.CategorieDsil",
        verbose_name="DSIL · Éligibilité de l'opération",
        on_delete=models.PROTECT,
        null=True,
    )
    demande_categorie_detr = models.ForeignKey(
        "gsl_demarches_simplifiees.CategorieDetr",
        verbose_name="Catégories prioritaires",
        on_delete=models.PROTECT,
        null=True,
    )

    demande_montant = models.DecimalField(
        "Montant de l'aide demandée (en euros)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    demande_autres_aides = models.ManyToManyField(
        "gsl_demarches_simplifiees.AutreAide",
        verbose_name="En 2024, comptez-vous solliciter d'autres aides publiques pour financer cette opération  ?",
        blank=True,
    )

    demande_autre_precision = models.TextField(
        "Autre - précisez le dispositif de financement concerné",
        blank=True,
    )
    demande_autre_numero_dossier = models.CharField(
        "Si votre dossier a déjà été déposé, précisez le numéro de dossier",
        blank=True,
    )
    demande_autre_dsil_detr = models.BooleanField(
        "Présentez-vous une autre opération au titre de la DETR/DSIL 2024 ?",
        null=True,
    )
    demande_priorite_dsil_detr = models.IntegerField(
        "Si oui, précisez le niveau de priorité de ce dossier.",
        null=True,
        blank=True,
    )
    # -- annotations
    annotations_contact = models.CharField(
        "Contact de l'agent instructeur à indiquer au demandeur",
        blank=True,
    )
    annotations_champ_libre_1 = models.TextField(
        "Champ libre pour le service instructeur 1",
        blank=True,
    )
    annotations_champ_libre_2 = models.TextField(
        "Champ libre pour le service instructeur 2",
        blank=True,
    )
    annotations_champ_libre_3 = models.TextField(
        "Champ libre pour le service instructeur 3",
        blank=True,
    )
    annotations_dotation = models.CharField(
        "Imputation budgétaire - Choix de la dotation",
        blank=True,
    )
    annotations_is_budget_vert = models.BooleanField(
        "Projet concourant à la transition écologique au sens budget vert", null=True
    )
    annotations_is_qpv = models.BooleanField("Projet situé en QPV", null=True)
    annotations_is_crte = models.BooleanField("Projet rattaché à un CRTE", null=True)
    annotations_is_frr = models.BooleanField("Projet situé en FRR", null=True)
    annotations_is_acv = models.BooleanField(
        "Projet rattaché à un programme Action coeurs de Ville (ACV)", null=True
    )
    annotations_is_pvd = models.BooleanField(
        "Projet rattaché à un programme Petites villes de demain (PVD)", null=True
    )
    annotations_is_va = models.BooleanField(
        "Projet rattaché à un programme Villages d'avenir", null=True
    )
    annotations_is_autre_zonage_local = models.BooleanField(
        "Projet rattaché à un autre zonage local", null=True
    )
    annotations_autre_zonage_local = models.CharField(
        "Zonage local", blank=True
    )  # "Précisez lequel." dans DN => le renseigner à la main via le BO
    annotations_is_contrat_local = models.BooleanField(
        "Projet rattaché à un contrat local", null=True
    )
    annotations_contrat_local = models.CharField(
        "Contrat local", blank=True
    )  # "Précisez lequel." dans DN => le renseigner à la main via le BO

    # DETR
    annotations_assiette_detr = models.DecimalField(
        "DETR - Montant des dépenses éligibles retenues (en euros)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    annotations_montant_accorde_detr = models.DecimalField(
        "DETR - Montant définitif de la subvention (en euros)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    annotations_taux_detr = models.DecimalField(
        "DETR - Taux de subvention (%)",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    # DSIL
    annotations_assiette_dsil = models.DecimalField(
        "DSIL - Montant des dépenses éligibles retenues (en euros)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    annotations_montant_accorde_dsil = models.DecimalField(
        "DSIL - Montant définitif de la subvention (en euros)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    annotations_taux_dsil = models.DecimalField(
        "DSIL - Taux de subvention (%)",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )

    _MAPPED_CHAMPS_FIELDS = (
        porteur_de_projet_nature,
        porteur_de_projet_departement,
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
        projet_zonage_autre,
        projet_contractualisation,
        projet_contractualisation_autre,
        environnement_transition_eco,
        environnement_objectifs,
        environnement_artif_sols,
        date_debut,
        date_achevement,
        finance_cout_total,
        finance_recettes,
        demande_renouvellement,
        demande_numero_demande_precedente,
        demande_dispositif_sollicite,
        demande_categorie_dsil,
        demande_categorie_detr,
        demande_montant,
        demande_autres_aides,
        demande_autre_precision,
        demande_autre_numero_dossier,
        demande_autre_dsil_detr,
        demande_priorite_dsil_detr,
    )
    _MAPPED_ANNOTATIONS_FIELDS = (
        annotations_contact,
        annotations_champ_libre_1,
        annotations_champ_libre_2,
        annotations_champ_libre_3,
        annotations_dotation,
        annotations_is_budget_vert,
        annotations_is_qpv,
        annotations_is_crte,
        annotations_is_frr,
        annotations_is_acv,
        annotations_is_pvd,
        annotations_is_va,
        annotations_is_autre_zonage_local,
        annotations_autre_zonage_local,
        annotations_is_contrat_local,
        annotations_contrat_local,
        annotations_assiette_detr,
        annotations_montant_accorde_detr,
        annotations_taux_detr,
        annotations_assiette_dsil,
        annotations_montant_accorde_dsil,
        annotations_taux_dsil,
    )
    MAPPED_FIELDS = _MAPPED_ANNOTATIONS_FIELDS + _MAPPED_CHAMPS_FIELDS

    objects = models.Manager.from_queryset(DossierQuerySet)()

    class Meta:
        verbose_name = "Dossier"

    def __str__(self):
        return f"Dossier {self.ds_number}"

    @property
    def url_on_ds(self):
        return f"https://demarche.numerique.gouv.fr/procedures/{self.ds_demarche_number}/dossiers/{self.ds_number}"

    @property
    def json_url(self):
        return reverse(
            "ds:view-dossier-json", kwargs={"dossier_ds_number": self.ds_number}
        )

    def get_projet_perimetre(self) -> Perimetre | None:
        """
        Retourne le périmètre du projet qui sera issu du dossier, à partir de
        l'arrondissement déclaré par le demandeur dans le formulaire DN
        (champ DN porteur_de_projet_arrondissement).

        À défaut d'arrondissement dans le département (cas des n°75 et 90)
        on retourne un périmètre départemental.

        :return: Perimetre
        """
        projet_departement, projet_arrondissement = None, None
        ds_arrondissement_declaratif = self.porteur_de_projet_arrondissement
        if ds_arrondissement_declaratif is not None:
            projet_arrondissement = ds_arrondissement_declaratif.core_arrondissement
            if projet_arrondissement:
                projet_departement = projet_arrondissement.departement
        elif self.porteur_de_projet_departement:
            ds_departement_declaratif = self.porteur_de_projet_departement
            projet_departement = ds_departement_declaratif.core_departement
            if projet_departement is None:
                logger.warning(
                    "Dossier is missing departement.",
                    extra={
                        "dossier_ds_number": self.ds_number,
                        "departement": ds_departement_declaratif,
                    },
                )
                return None
            arrondissement_count = projet_departement.arrondissement_set.count()
            # Dans un département avec plusieurs arrondissements, les dossiers DS
            # devraient porter un arrondissement renseigné. => Lever une alerte
            if arrondissement_count > 1:
                logger.warning(
                    "Dossier is missing arrondissement.",
                    extra={
                        "dossier_ds_number": self.ds_number,
                        "arrondissement": self.porteur_de_projet_arrondissement,
                        "departement": projet_departement,
                    },
                )
            elif arrondissement_count == 1:
                # S'il n'y a qu'un seul arrondissement dans le département :
                # on prend le département renseigné
                projet_arrondissement = projet_departement.arrondissement_set.get()
        if projet_arrondissement or projet_departement:
            return Perimetre.objects.get_or_create(
                departement=projet_departement,
                arrondissement=projet_arrondissement,
                region_id=projet_departement.region_id,
            )[0]
        return None

    @property
    def taux_demande(self):
        if self.finance_cout_total and self.demande_montant:
            return round(self.demande_montant / self.finance_cout_total * 100, 2)
        return None

    @property
    def porteur_fullname(self):
        return f"{self.porteur_de_projet_nom} {self.porteur_de_projet_prenom}"

    @property
    def demande_montant_is_greater_than_min_montant_for_detr_commission(self):
        if self.demande_montant is None:
            return False
        return self.demande_montant >= MIN_DEMANDE_MONTANT_FOR_AVIS_DETR

    @property
    def is_sans_pieces(self) -> bool:
        return "SANS" in self.demande_renouvellement

    @property
    def dotations_demande(self):
        dotations = []

        if not self.demande_dispositif_sollicite:
            return dotations

        if DOTATION_DETR in self.demande_dispositif_sollicite:
            dotations.append(DOTATION_DETR)
        if DOTATION_DSIL in self.demande_dispositif_sollicite:
            dotations.append(DOTATION_DSIL)

        if not dotations:
            logger.warning(
                "Champ demande_dispositif_sollicite invalide.",
                extra={
                    "dossier_ds_number": self.ds_number,
                    "value": self.demande_dispositif_sollicite,
                },
            )

        return dotations

    @property
    def has_annotations_champ_libre(self):
        return (
            bool(self.annotations_champ_libre_1)
            or bool(self.annotations_champ_libre_2)
            or bool(self.annotations_champ_libre_3)
        )


class DsChoiceLibelle(TimestampedModel):
    label = models.CharField("Libellé", unique=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.label


class NaturePorteurProjet(DsChoiceLibelle):
    EPCI = "epci"
    COMMUNES = "communes"
    AUTRE = "autre"
    TYPE_CHOICES = (
        (EPCI, "EPCI"),
        (COMMUNES, "Communes"),
        (AUTRE, "Autre"),
    )
    type = models.CharField(max_length=8, choices=TYPE_CHOICES, blank=True)

    class Meta:
        verbose_name = "Nature du porteur de projet"
        verbose_name_plural = "Natures de porteur de projet"


class Departement(DsChoiceLibelle):
    core_departement = models.ForeignKey(
        CoreDepartement,
        related_name="ds_departements",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Département INSEE",
    )

    class Meta:
        verbose_name = "Département DS"
        verbose_name_plural = "Départements DS"


class Arrondissement(DsChoiceLibelle):
    core_arrondissement = models.ForeignKey(
        CoreArrondissement,
        related_name="ds_arrondissements",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Arrondissement INSEE",
    )

    class Meta:
        verbose_name = "Arrondissement DS"
        verbose_name_plural = "Arrondissements DS"


class ProjetZonage(DsChoiceLibelle):
    pass


class ProjetContractualisation(DsChoiceLibelle):
    pass


class ObjectifEnvironnemental(DsChoiceLibelle):
    pass


class CategorieQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)


class CategorieManager(models.Manager.from_queryset(CategorieQuerySet)):
    pass


class Categorie(TimestampedModel):
    demarche = models.ForeignKey(
        Demarche, on_delete=models.PROTECT, verbose_name="Démarche"
    )
    label = models.CharField("Libellé")
    rank = models.IntegerField("Rang", null=True)
    active = models.BooleanField("Active", default=True)
    deactivated_at = models.DateTimeField(
        "Date de désactivation", null=True, blank=True
    )

    objects = CategorieManager()

    class Meta:
        abstract = True

    def deactivate(self):
        self.active = False
        self.deactivated_at = timezone.now()
        self.save()


class CategorieDetr(Categorie):
    parent_label = models.CharField("Libellé de la catégorie parente", blank=True)
    departement = models.ForeignKey(
        CoreDepartement,
        verbose_name="Département",
        on_delete=models.PROTECT,
        related_name="categories_detr",
    )

    class Meta:
        verbose_name = "Catégorie DETR"
        verbose_name_plural = "Catégories DETR"
        constraints = (
            models.UniqueConstraint(
                fields=("label", "demarche", "departement"),
                name="unique_categorie_detr_label_per_demarche_departement",
                nulls_distinct=False,
            ),
        )

    def __str__(self):
        return f"Catégorie DETR {self.pk} - {self.label}"


class CategorieDsil(Categorie):
    class Meta:
        verbose_name = "Catégorie DSIL"
        verbose_name_plural = "Catégories DSIL"
        constraints = (
            models.UniqueConstraint(
                fields=("label", "demarche"),
                name="unique_categorie_dsil_label_per_demarche",
                nulls_distinct=False,
            ),
        )

    def __str__(self):
        return f"Catégorie DSIL {self.pk} - {self.label}"


class AutreAide(DsChoiceLibelle):
    pass


class Profile(TimestampedModel):
    ds_id = models.CharField("Identifiant DS", unique=True)
    ds_email = models.EmailField("E-mail", unique=True)

    class Meta:
        verbose_name = "Profil DS"
        verbose_name_plural = "Profils DS"

    def __str__(self):
        return f"Profil {self.ds_email}"


def mapping_field_choices():
    return tuple(
        (field.name, f"{field.name} - {field.verbose_name}")
        for field in Dossier.MAPPED_FIELDS
    )


class FieldMappingForComputer(TimestampedModel):
    demarche = models.ForeignKey(Demarche, on_delete=models.CASCADE)
    ds_field_id = models.CharField("ID du champ DS")
    ds_field_label = models.CharField(
        "Libellé DS",
        help_text="Libellé au moment où ce champ a été rencontré pour la première fois — il a pu changer depuis !",
    )
    ds_field_type = models.CharField("Type de champ DS")
    django_field = models.CharField(
        "Champ Django", choices=mapping_field_choices, blank=True
    )

    class Meta:
        verbose_name = "Correspondance technique"
        verbose_name_plural = "Correspondances techniques"
        constraints = (
            models.UniqueConstraint(
                fields=("demarche", "ds_field_id"),
                name="unique_ds_field_id_per_demarche",
            ),
        )

    def __str__(self):
        return f"Correspondance technique {self.pk}"

    def django_field_label(self):
        if self.django_field:
            return Dossier._meta.get_field(self.django_field).verbose_name
        return None

    def django_field_type(self):
        if self.django_field:
            return str(Dossier._meta.get_field(self.django_field).__class__)[32:-2]
        return None
