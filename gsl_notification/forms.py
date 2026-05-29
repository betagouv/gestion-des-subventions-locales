import os
from functools import cached_property
from pathlib import Path

from django import forms
from django.conf import settings
from django.db import transaction
from django.template.defaultfilters import pluralize
from django.utils import timezone
from dsfr.forms import DsfrBaseForm

from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService
from gsl_notification.models import (
    Annexe,
    Arrete,
    LettreEtArreteSignes,
    LettreNotification,
    ModeleDocument,
)
from gsl_notification.utils import (
    get_generated_document_class,
    get_modele_class,
    get_modele_perimetres,
    merge_documents_into_pdf,
    replace_mentions_in_html,
)
from gsl_notification.validators import document_file_validator
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import (
    ARRETE,
    LETTRE,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
)
from gsl_projet.models import Projet


class RadioSelect(forms.RadioSelect):
    """
    The class name needs to be RadioSelect for DsfrBaseForm to do its magic.
    """

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        if not value:
            attrs = {**(attrs or {}), "disabled": "disabled"}
            label = {
                "label": label,
                "help_text": "Le document a déjà été généré pour cette dotation.",
            }

        return super().create_option(
            name, value, label, selected if value else False, index, attrs=attrs
        )


class BaseChooseDocumentTypeForm(DsfrBaseForm, forms.Form):
    document = forms.ChoiceField(
        widget=RadioSelect,
        required=True,
        choices=(
            (
                model.document_type,
                model._meta.verbose_name,
            )
            for model in (Arrete, LettreNotification)
        ),
        label="Type de document",
    )


class ChooseDocumentTypeForGenerationForm(BaseChooseDocumentTypeForm):
    def __init__(self, *args, instance, **kwargs):
        # Not a ModelForm, but we get instance from the view which is an UpdateView.
        super().__init__(*args, **kwargs)
        self.fields["document"].choices = [
            (
                (
                    ""
                    if model.objects.filter(
                        programmation_projet__dotation_projet=dp
                    ).exists()
                    else f"{model.document_type}-{dp.dotation}"
                ),
                f"{model._meta.verbose_name} {dp.dotation}",
            )
            for model in (Arrete, LettreNotification)
            for dp in instance.dotationprojet_set.filter(status=PROJET_STATUS_ACCEPTED)
        ]

    def clean_document(self):
        doc_type, dotation = self.cleaned_data["document"].split("-")
        return {
            "type": doc_type,
            "dotation": dotation,
        }


class ChooseDocumentTypeForMultipleGenerationForm(BaseChooseDocumentTypeForm):
    pass


class ChooseDocumentTypeForUploadForm(BaseChooseDocumentTypeForm):
    def __init__(self, *args, instance, **kwargs):
        # Not a ModelForm, but we get instance from the view which is an UpdateView.
        super().__init__(*args, **kwargs)
        self.instance = instance
        choices = []
        for dp in instance.dotationprojet_set.filter(status=PROJET_STATUS_ACCEPTED):
            # Check if ProgrammationProjet exists for this dotation
            try:
                prog_projet = ProgrammationProjet.objects.get(
                    dotation_projet=dp, dotation_projet__projet=self.instance
                )
                # LettreEtArreteSignes (disable if already exists)
                existing_arrete = hasattr(prog_projet, "lettre_et_arrete_signes")

                choices.append(
                    (
                        (
                            ""
                            if existing_arrete
                            else f"lettre_et_arrete_signes-{dp.dotation}"
                        ),
                        f"Lettre et arrêté signés {dp.dotation.upper()}",
                    )
                )

                # Annexe (always enabled, multiple allowed)
                choices.append(
                    (
                        f"annexe-{dp.dotation}",
                        f"Annexe {dp.dotation.upper()}",
                    )
                )
            except ProgrammationProjet.DoesNotExist:
                continue

        self.fields["document"].choices = choices

    def clean_document(self):
        doc_type, dotation = self.cleaned_data["document"].split("-")
        return {
            "type": doc_type,
            "dotation": dotation,
        }


class ArreteForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Arrete
        fields = ("content", "created_by", "programmation_projet", "modele")


class LettreNotificationForm(ArreteForm):
    class Meta:
        model = LettreNotification
        fields = ("content", "created_by", "programmation_projet", "modele")


class ArreteEtLettreSigneForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = LettreEtArreteSignes
        fields = ("file", "created_by", "programmation_projet")


class AnnexeForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = Annexe
        fields = ("file", "created_by", "programmation_projet")


class ModeleDocumentStepZeroForm(DsfrBaseForm):
    TYPE_CHOICES = (
        (ARRETE, "Arrêté attributif"),
        (LETTRE, "Lettre de notification"),
    )
    type = forms.ChoiceField(
        label="Type de document", choices=TYPE_CHOICES, widget=forms.RadioSelect
    )


class ModeleDocumentStepOneForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = ModeleDocument
        fields = ("name", "description")


class ModeleDocumentStepTwoForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = ModeleDocument
        fields = ("logo", "logo_alt_text", "top_right_text")


class ModeleDocumentStepThreeForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = ModeleDocument
        fields = ("content",)


class AnnexeChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Annexe):
        return f"Annexe - {obj.name}"


class NotificationMessageForm(DsfrBaseForm, forms.ModelForm):
    annexes = AnnexeChoiceField(
        widget=forms.CheckboxSelectMultiple,
        queryset=Annexe.objects.none(),
        label="Pièces jointes",
        required=False,
    )
    justification = forms.CharField(
        label="Justification de l'acceptation du dossier (facultatif)",
        required=False,
        widget=forms.Textarea,
    )
    nom_du_fichier = forms.CharField(
        label="Nom du fichier (facultatif)",
        required=False,
        widget=forms.TextInput,
        help_text="Si non renseigné, le nom du premier document signé importé sera utilisé.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["annexes"].queryset = Annexe.objects.filter(
            programmation_projet__dotation_projet__projet=self.instance
        )
        first_lettre = LettreEtArreteSignes.objects.filter(
            programmation_projet__dotation_projet__projet=self.instance
        ).first()
        if first_lettre:
            self[
                "nom_du_fichier"
            ].help_text = f"Si non renseigné, le nom du premier document signé importé sera utilisé : « {first_lettre.name} »."
            # We don't use self.fields because DsfrBaseForm adds the necessary classes on relevant fields in __init__, so we need to update the help_text on the already initialized field.

    def clean_nom_du_fichier(self):
        value = self.cleaned_data["nom_du_fichier"].strip()
        if not value:
            return value
        if Path(value).name != value:
            raise forms.ValidationError(
                'Le nom du fichier ne peut pas contenir de "/".'
            )
        stem, ext = os.path.splitext(value)
        if ext.lower() == ".pdf":
            return stem
        if ext:
            raise forms.ValidationError(
                "Le nom du fichier ne peut pas avoir une extension autre que .pdf."
            )
        return value

    def save(self, user):
        from gsl_historique.models import ProjetAction

        lettres = LettreEtArreteSignes.objects.filter(
            programmation_projet__dotation_projet__projet=self.instance
        )
        nom = self.cleaned_data.get("nom_du_fichier")
        if not nom:
            nom = (
                os.path.splitext(lettres.first().name)[0]
                if lettres.exists()
                else "documents"
            )
        filename = nom + ".pdf"

        justificatif_file = merge_documents_into_pdf(
            [
                *lettres,
                *self.cleaned_data["annexes"],
            ],
            filename=filename,
        )

        # Dossier was recently refreshed DN
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
        if self.instance.dossier_ds.ds_state == Dossier.STATE_EN_CONSTRUCTION:
            ds = DsService()
            ds.passer_en_instruction(dossier=self.instance.dossier_ds, user=user)
        with transaction.atomic():
            self.instance.notified_at = timezone.now()
            self.instance.save()
            # TODO use DSService
            DsMutator().dossier_accepter(
                self.instance.dossier_ds,
                user.ds_id,
                motivation=self.cleaned_data.get("justification", ""),
                document=justificatif_file,
            )
            ProjetAction.objects.create(
                projet=self.instance,
                action_type=ProjetAction.TYPE_NOTIFIED,
                actor=user,
                source=ProjetAction.SOURCE_TURGOT,
            )

            return self.instance

    class Meta:
        model = Projet
        fields = ()


class RefusedDismissedNotificationForm(DsfrBaseForm, forms.ModelForm):
    """
    Sends the refusal/classement notification to Démarches Numériques.

    The form is rendered for projets whose resolved status is REFUSED or
    DISMISSED (no accepted dotation).
    """

    justification = forms.CharField(
        label="Motivation envoyée au demandeur (obligatoire)",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    justification_file = forms.FileField(
        label="Ajouter un justificatif (optionnel)",
        validators=[document_file_validator],
        help_text=f"Taille maximale {settings.MAX_POST_FILE_SIZE_IN_MO} Mo. Formats supportés : jpg, png, pdf.",
        required=False,
    )

    class Meta:
        model = Projet
        fields = ()

    @transaction.atomic
    def save(self, user):
        from gsl_historique.models import ProjetAction

        projet = self.instance
        dossier = projet.dossier_ds
        ds = DsService()

        # Dossier was recently refreshed DN thanks to the up-to-date check.
        # Race conditions remain possible, but should be rare enough and just
        # fail without any side effect.
        if dossier.ds_state == Dossier.STATE_EN_CONSTRUCTION:
            ds.passer_en_instruction(dossier=dossier, user=user)

        if projet.status == PROJET_STATUS_DISMISSED:
            ds.dismiss_in_ds(
                dossier,
                user,
                motivation=self.cleaned_data["justification"],
                document=self.cleaned_data.get("justification_file"),
            )
        else:
            ds.refuser_in_ds(
                dossier,
                user,
                motivation=self.cleaned_data["justification"],
                document=self.cleaned_data.get("justification_file"),
            )

        projet.notified_at = timezone.now()
        projet.save()
        ProjetAction.objects.create(
            projet=projet,
            action_type=ProjetAction.TYPE_NOTIFIED,
            actor=user,
            source=ProjetAction.SOURCE_TURGOT,
        )
        return projet


# -- Multi-projet document generation modal forms --

ARRETE_ET_LETTRE = "arrete_et_lettre"

EXPORT_FORMAT_ONE_PDF_PER_DOC = "un_pdf_par_document"
EXPORT_FORMAT_ONE_PDF_ALL = "un_seul_pdf_ensemble"
EXPORT_FORMAT_ONE_PDF_PER_PROJECT = "un_pdf_par_projet"
EXPORT_FORMAT_ONE_PDF_ALL_GROUPED = "un_seul_pdf_groupe_par_projet"


class ProgrammationProjetMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Hidden, CSV-encoded ModelMultipleChoiceField for ProgrammationProjet."""

    widget = forms.HiddenInput

    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, str):
            return [int(i) for i in value.split(",") if i.strip().isdigit()]
        return [int(i) for i in value if str(i).strip().isdigit()]

    def clean(self, value):
        # HiddenInput posts a CSV string; normalize to a list of pks before the
        # parent's clean (which expects list/tuple after prepare_value).
        if isinstance(value, str):
            value = self.to_python(value)
        return super().clean(value)


SELECTED_TYPES_BY_CHOICE: dict[str, frozenset[str]] = {
    ARRETE: frozenset({ARRETE}),
    LETTRE: frozenset({LETTRE}),
    ARRETE_ET_LETTRE: frozenset({ARRETE, LETTRE}),
}


class BaseGenerateDocumentsForm(DsfrBaseForm, forms.Form):
    """Resolves the programmation_projets the wizard operates on."""

    def __init__(self, *args, user, dotation, request, **kwargs):
        self.user = user
        self.dotation = dotation
        self.request = request
        super().__init__(*args, **kwargs)

    @cached_property
    def selected_types(self) -> frozenset[str]:
        return SELECTED_TYPES_BY_CHOICE[self.document_type]


class GenerateDocumentsLaunchForm(BaseGenerateDocumentsForm):
    """Validates the trigger button POST: resolves ids and detects mismatches."""

    ids = ProgrammationProjetMultipleChoiceField(
        queryset=ProgrammationProjet.objects.none(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ids"].queryset = (
            ProgrammationProjet.objects.active()
            .visible_to_user(self.user)
            .can_generate_documents()
            .filter(dotation_projet__dotation=self.dotation)
            .select_related("dotation_projet__projet")
        )

    def clean_ids(self):
        ids = self.cleaned_data.get("ids") or []
        if not ids:
            filterset = ProgrammationProjetFilters(
                data=self.request.GET, request=self.request
            )
            ids = filterset.qs.can_generate_documents()
        if not ids:
            raise forms.ValidationError("Aucun projet à notifier.", code="no_projects")
        return ids


class GenerateDocumentsStep1Form(BaseGenerateDocumentsForm):
    DOCUMENT_TYPE_CHOICES = [
        (ARRETE, "Les arrêtés"),
        (LETTRE, "Les lettres de notification"),
        (ARRETE_ET_LETTRE, "Les deux"),
    ]

    document_type = forms.ChoiceField(
        choices=DOCUMENT_TYPE_CHOICES,
        widget=forms.RadioSelect,
        required=True,
        label="Documents à générer",
        error_messages={
            "required": "Type de document inconnu",
            "invalid_choice": "Type de document inconnu",
        },
    )


class GenerateDocumentsStep2Form(BaseGenerateDocumentsForm):
    STRATEGY_CONSERVER = "conserver"
    STRATEGY_REMPLACER = "remplacer"

    # Plural noun per document type; (LETTRE, ARRETE) iteration order keeps
    # "lettres" before "arrêtés" everywhere (selected_types is an unordered set).
    _DOC_TYPE_NOUNS = {LETTRE: "lettres", ARRETE: "arrêtés"}

    @staticmethod
    def _modele_field(queryset, label):
        return forms.ModelChoiceField(
            queryset=queryset,
            required=True,
            empty_label="Sélectionner un modèle",
            error_messages={
                "required": "Veuillez sélectionner un modèle.",
                "invalid_choice": "Modèle introuvable.",
            },
            label=label,
        )

    def __init__(self, *args, document_type, programmation_projets, **kwargs):
        super().__init__(*args, **kwargs)
        self.document_type = document_type
        self.programmation_projets = programmation_projets

        # Conserver/Remplacer first: its "…ci-dessous" wording refers to the
        # model dropdowns rendered just below it.
        if self.has_existing_docs():
            self.fields["overwrite_strategy"] = forms.ChoiceField(
                choices=[
                    (self.STRATEGY_CONSERVER, self._conserver_label),
                    (self.STRATEGY_REMPLACER, self._remplacer_label),
                ],
                widget=forms.RadioSelect,
                required=True,
                initial=self.STRATEGY_CONSERVER,
                label=self._overwrite_field_label,
                help_text="« Conserver » permet de ne pas régénérer les documents existants.",
            )

        if self.has_lettre:
            self.fields["modele_lettre_id"] = self._modele_field(
                self.modeles_lettre,
                "Modèle pour les lettres de notification",
            )
        if self.has_arrete:
            self.fields["modele_arrete_id"] = self._modele_field(
                self.modeles_arrete, "Modèle pour les arrêtés"
            )

    @cached_property
    def _selected_nouns(self) -> list[str]:
        return [
            self._DOC_TYPE_NOUNS[t]
            for t in (LETTRE, ARRETE)
            if t in self.selected_types
        ]

    @property
    def _overwrite_field_label(self) -> str:
        nouns = " ou ".join(f"des {n}" for n in self._selected_nouns)
        return f"Que voulez-vous faire avec les projets ayant déjà {nouns} ?"

    @property
    def _conserver_label(self) -> str:
        nouns = " et ".join(f"les {n}" for n in self._selected_nouns)
        # Feminine agreement only when "lettres" is the sole type.
        fem = self.has_lettre and not self.has_arrete
        return f"Conserver {nouns} existant{pluralize(fem, 'es,s')}"

    @property
    def _remplacer_label(self) -> str:
        nouns = " et ".join(f"les {n}" for n in self._selected_nouns)
        fem = self.has_lettre and not self.has_arrete
        # "toutes/tous" agrees with the first noun ("lettres" when present).
        quantifier = f"tou{pluralize(self.has_lettre, 'tes,s')}"
        return (
            f"Remplacer {quantifier} {nouns} par "
            f"{pluralize(fem, 'celles,ceux')} "
            f"sélectionné{pluralize(fem, 'es,s')} ci-dessous"
        )

    @cached_property
    def has_arrete(self) -> bool:
        return ARRETE in self.selected_types

    @cached_property
    def has_lettre(self) -> bool:
        return LETTRE in self.selected_types

    @cached_property
    def modeles_arrete(self):
        return self._modeles_queryset(ARRETE) if self.has_arrete else None

    @cached_property
    def modeles_lettre(self):
        return self._modeles_queryset(LETTRE) if self.has_lettre else None

    @cached_property
    def existing_arrete_count(self) -> int:
        if not self.has_arrete:
            return 0
        return Arrete.objects.filter(
            programmation_projet__in=self.programmation_projets
        ).count()

    @cached_property
    def existing_lettre_count(self) -> int:
        if not self.has_lettre:
            return 0
        return LettreNotification.objects.filter(
            programmation_projet__in=self.programmation_projets
        ).count()

    def _modeles_queryset(self, document_type):
        perimetres = get_modele_perimetres(self.dotation, self.user.perimetre)
        return get_modele_class(document_type).objects.filter(
            dotation=self.dotation, perimetre__in=perimetres
        )

    def has_existing_docs(self):
        return self.existing_arrete_count + self.existing_lettre_count > 0


class GenerateDocumentsStep3Form(BaseGenerateDocumentsForm):
    EXPORT_FORMAT_CHOICES_SINGLE = [
        (EXPORT_FORMAT_ONE_PDF_ALL, "Un seul PDF pour l'ensemble"),
        (EXPORT_FORMAT_ONE_PDF_PER_DOC, "Un PDF par document"),
    ]

    EXPORT_FORMAT_CHOICES_BOTH = [
        (
            EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
            "Un seul PDF pour l'ensemble groupé par projet",
        ),
        (EXPORT_FORMAT_ONE_PDF_PER_PROJECT, "Un PDF par projet (lettre + arrêté)"),
        (EXPORT_FORMAT_ONE_PDF_PER_DOC, "Un PDF par document"),
    ]

    export_format = forms.ChoiceField(
        choices=[],
        widget=forms.RadioSelect,
        required=True,
        label="Format",
        error_messages={
            "required": "Veuillez sélectionner un format d'export.",
            "invalid_choice": "Veuillez sélectionner un format d'export.",
        },
    )

    with_qr_code = forms.BooleanField(
        required=False,
        initial=True,
        label="Inclure le QR code de suivi sur chaque page",
        help_text=(
            "Le QR code permet de rattacher automatiquement un document "
            "signé scanné au bon projet. Il est retiré lors de l'import."
        ),
    )

    def __init__(self, *args, document_type, **kwargs):
        super().__init__(*args, **kwargs)
        self.document_type = document_type
        self.fields["export_format"].choices = (
            self.EXPORT_FORMAT_CHOICES_BOTH
            if len(self.selected_types) > 1
            else self.EXPORT_FORMAT_CHOICES_SINGLE
        )


class GenerateDocumentsCreateForm(BaseGenerateDocumentsForm):
    """
    Save-action form for the wizard's final step. Receives data already cleaned
    and validated by the launch/step1/step2/step3 forms via __init__ kwargs and
    performs the document creation.
    """

    def __init__(
        self,
        *args,
        document_type,
        programmation_projets,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.document_type = document_type
        self.programmation_projets = programmation_projets

    def _log_doc_action(self, pp, document_class):
        from gsl_historique.models import ProjetAction

        ProjetAction.objects.create(
            projet=pp.dotation_projet.projet,
            action_type=ProjetAction.TYPE_DOC_GENERATED,
            actor=self.user,
            source=ProjetAction.SOURCE_TURGOT,
            dotation=pp.dotation_projet.dotation,
            document_name=document_class._meta.verbose_name.capitalize(),
        )

    @transaction.atomic
    def save(self, *, modele_arrete, modele_lettre, overwrite_strategy):
        pps = self.programmation_projets

        modele_by_type = {ARRETE: modele_arrete, LETTRE: modele_lettre}
        for doc_type in self.selected_types:
            self._create_documents_of_type(
                pps, doc_type, modele_by_type[doc_type], overwrite_strategy
            )

        return list(
            ProgrammationProjet.objects.active()
            .select_related(
                "arrete",
                "arrete__modele",
                "lettre_notification",
                "lettre_notification__modele",
                "lettre_et_arrete_signes",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
                "enveloppe",
                "dotation_projet__projet__dossier_ds__ds_demandeur",
            )
            .prefetch_related(
                "annexes",
            )
            .filter(pk__in=pps)
        )

    def _create_documents_of_type(
        self, programmation_projets, document_type, modele, overwrite_strategy
    ):
        document_class = get_generated_document_class(document_type)

        if overwrite_strategy == GenerateDocumentsStep2Form.STRATEGY_REMPLACER:
            document_class.objects.filter(
                programmation_projet__in=programmation_projets
            ).delete()
            pps_to_create = programmation_projets
        else:
            pps_to_create = (
                ProgrammationProjet.objects.active()
                .filter(pk__in=programmation_projets)
                .exclude(
                    pk__in=document_class.objects.values("programmation_projet_id")
                )
            )

        for pp in pps_to_create:
            document_class(
                programmation_projet=pp,
                modele=modele,
                created_by=self.user,
                content=replace_mentions_in_html(modele.content, pp),
            ).save()
            self._log_doc_action(pp, document_class)
