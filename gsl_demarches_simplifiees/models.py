from django.db import models
from django.urls import reverse

from gsl_core.models import Adresse, Perimetre
from gsl_core.models import Arrondissement as CoreArrondissement
from gsl_core.models import Departement as CoreDepartement
from gsl_projet.constants import MIN_DEMANDE_MONTANT_FOR_AVIS_DETR


class DsModel(models.Model):
    created_at = models.DateTimeField("Date de création", auto_now_add=True)
    updated_at = models.DateTimeField("Date de modification", auto_now=True)

    class Meta:
        abstract = True


class Demarche(DsModel):
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

    perimetre = models.ForeignKey(
        Perimetre,
        on_delete=models.PROTECT,
        verbose_name="Périmètre",
        null=True,
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


class Dossier(DsModel):
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

    raw_ds_data = models.JSONField("Données DS brutes", null=True, blank=True)

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
    projet_contractualisation = models.ManyToManyField(
        "gsl_demarches_simplifiees.ProjetContractualisation",
        verbose_name="Contractualisation : le projet est-il inscrit dans un ou plusieurs contrats avec l'Etat ?",
        blank=True,
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
    demande_annee_precedente = models.BooleanField(
        "Avez-vous déjà présenté cette opération au titre de campagnes DETR/DSIL en 2023 ?",
        null=True,
    )
    demande_numero_demande_precedente = models.CharField(
        "Précisez le numéro du dossier déposé antérieurement",
        blank=True,
    )

    demande_dispositif_sollicite = models.CharField(
        "Dispositif de financement sollicité",
        blank=True,
    )
    demande_eligibilite_detr = models.ManyToManyField(
        "gsl_demarches_simplifiees.CritereEligibiliteDetr",
        verbose_name="Eligibilité de l'opération à la DETR",
        blank=True,
    )

    demande_eligibilite_dsil = models.ManyToManyField(
        "gsl_demarches_simplifiees.CritereEligibiliteDsil",
        verbose_name="Eligibilité de l'opération à la DSIL",
        blank=True,
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
    annotations_champ_libre = models.TextField(
        "Champ libre pour le service instructeur",
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
    # TODO remove these three fields at the end of DUN dev
    annotations_assiette = models.DecimalField(
        "Montant des dépenses éligibles retenues (€)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    annotations_montant_accorde = models.DecimalField(
        "Montant définitif de la subvention (€)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    annotations_taux = models.DecimalField(
        "Taux de subvention (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
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
    _MAPPED_ANNOTATIONS_FIELDS = (
        annotations_contact,
        annotations_champ_libre,
        annotations_dotation,
        annotations_is_budget_vert,
        annotations_is_qpv,
        annotations_is_crte,
        annotations_assiette_detr,
        annotations_montant_accorde_detr,
        annotations_taux_detr,
        annotations_assiette_dsil,
        annotations_montant_accorde_dsil,
        annotations_taux_dsil,
    )
    MAPPED_FIELDS = _MAPPED_ANNOTATIONS_FIELDS + _MAPPED_CHAMPS_FIELDS

    class Meta:
        verbose_name = "Dossier"

    def __str__(self):
        return f"Dossier {self.ds_number}"

    @property
    def url_on_ds(self):
        return f"https://demarche.numerique.gouv.fr/procedures/{self.ds_demarche.ds_number}/dossiers/{self.ds_number}"

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
        on retourne un périmètre départemental. @todo

        :return: Perimetre
        """
        projet_departement, projet_arrondissement = None, None
        ds_arrondissement_declaratif = self.porteur_de_projet_arrondissement
        if ds_arrondissement_declaratif is not None:
            projet_arrondissement = ds_arrondissement_declaratif.core_arrondissement
            if projet_arrondissement:
                projet_departement = projet_arrondissement.departement
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
    def demande_montant_is_greater_thant_min_montant_for_detr_commission(self):
        return self.demande_montant >= MIN_DEMANDE_MONTANT_FOR_AVIS_DETR


class DsChoiceLibelle(DsModel):
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


class CritereEligibiliteDetr(DsChoiceLibelle):
    label = models.CharField("Libellé", unique=False)

    demarche = models.ForeignKey(
        Demarche, on_delete=models.PROTECT, null=True, verbose_name="Démarche"
    )
    demarche_revision = models.CharField(
        blank=True, default="", verbose_name="Révision"
    )
    detr_category = models.ForeignKey(
        "gsl_projet.CategorieDetr",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Catégorie d’opération DETR",
    )

    class Meta:
        verbose_name = "Catégorie DETR"
        verbose_name_plural = "Catégories DETR"
        constraints = (
            models.UniqueConstraint(
                fields=("label", "demarche", "demarche_revision"),
                name="unique_%(class)s_label_per_demarche_revision",
                nulls_distinct=False,
            ),
        )


class CritereEligibiliteDsil(DsChoiceLibelle):
    class Meta:
        verbose_name = "Catégorie DSIL"
        verbose_name_plural = "Catégories DSIL"


class AutreAide(DsChoiceLibelle):
    pass


class Profile(DsModel):
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
    ds_field_id = models.CharField("ID du champ DS")
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
