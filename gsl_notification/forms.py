from functools import cached_property

from django import forms
from django.db import transaction
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
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import ARRETE, LETTRE, PROJET_STATUS_ACCEPTED
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

    def save(self, user):
        justificatif_file = merge_documents_into_pdf(
            [
                *LettreEtArreteSignes.objects.filter(
                    programmation_projet__dotation_projet__projet=self.instance
                ),
                *self.cleaned_data["annexes"],
            ]
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

            return self.instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["annexes"].queryset = Annexe.objects.filter(
            programmation_projet__dotation_projet__projet=self.instance
        )

    class Meta:
        model = Projet
        fields = ()


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
            ProgrammationProjet.active.visible_to_user(self.user)
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

    OVERWRITE_STRATEGY_CHOICES = [
        (STRATEGY_CONSERVER, "Conserver"),
        (STRATEGY_REMPLACER, "Remplacer"),
    ]

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

        if self.has_arrete:
            self.fields["modele_arrete_id"] = self._modele_field(
                self.modeles_arrete, "Modèle pour les arrêtés"
            )
        if self.has_lettre:
            self.fields["modele_lettre_id"] = self._modele_field(
                self.modeles_lettre,
                "Modèle pour les lettres de notification",
            )

        if self.has_existing_docs():
            self.fields["overwrite_strategy"] = forms.ChoiceField(
                choices=self.OVERWRITE_STRATEGY_CHOICES,
                widget=forms.RadioSelect,
                required=True,
                initial=self.STRATEGY_CONSERVER,
                label=f"Que voulez-vous faire avec les projets ayant déjà {
                    ' ou '.join(
                        [
                            *(['une lettre'] if LETTRE in self.selected_types else []),
                            *(['un arrêté'] if ARRETE in self.selected_types else []),
                        ]
                    )
                } ?",
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

    @transaction.atomic
    def save(self, *, modele_arrete, modele_lettre, overwrite_strategy):
        pps = self.programmation_projets

        modele_by_type = {ARRETE: modele_arrete, LETTRE: modele_lettre}
        for doc_type in self.selected_types:
            self._create_documents_of_type(
                pps, doc_type, modele_by_type[doc_type], overwrite_strategy
            )

        return list(
            ProgrammationProjet.active.select_related(
                "arrete", "lettre_notification", "lettre_et_arrete_signes"
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
            pps_to_create = ProgrammationProjet.active.filter(
                pk__in=programmation_projets
            ).exclude(pk__in=document_class.objects.values("programmation_projet_id"))

        for pp in pps_to_create:
            document_class(
                programmation_projet=pp,
                modele=modele,
                created_by=self.user,
                content=replace_mentions_in_html(modele.content, pp),
            ).save()
