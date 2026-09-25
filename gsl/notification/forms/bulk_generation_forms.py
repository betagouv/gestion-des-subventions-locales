from functools import cached_property

from django import forms
from django.db import transaction
from django.template.defaultfilters import pluralize
from dsfr.forms import DsfrBaseForm

from gsl.historique.models import ProjetAction
from gsl.notification.models import (
    GENERATED_DOCUMENTS,
    MODELES,
    ExportJob,
    ModeleDocument,
)
from gsl.notification.utils import get_modele_perimetres, replace_mentions_in_html
from gsl.programmation.utils.programmation_projet_filters import ProgrammationFilters
from gsl.projet.constants import ARRETE, LETTRE, LETTRE_REFUS
from gsl.projet.models import EnveloppeProjet, EnveloppeProjetQuerySet

ARRETE_ET_LETTRE = ExportJob.DOCUMENT_TYPE_ARRETE_ET_LETTRE

EXPORT_FORMAT_ONE_PDF_PER_DOC = ExportJob.EXPORT_FORMAT_ONE_PDF_PER_DOC
EXPORT_FORMAT_ONE_PDF_ALL = ExportJob.EXPORT_FORMAT_ONE_PDF_ALL
EXPORT_FORMAT_ONE_PDF_PER_PROJECT = ExportJob.EXPORT_FORMAT_ONE_PDF_PER_PROJECT
EXPORT_FORMAT_ONE_PDF_ALL_GROUPED = ExportJob.EXPORT_FORMAT_ONE_PDF_ALL_GROUPED


class EnveloppeProjetMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Hidden, CSV-encoded ModelMultipleChoiceField for EnveloppeProjet."""

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
    LETTRE_REFUS: frozenset({LETTRE_REFUS}),
}

# Canonical display order, used everywhere several document types are listed
# together: lettres before arrêtés before refus.
DOCUMENT_TYPE_DISPLAY_ORDER = (LETTRE, ARRETE, LETTRE_REFUS)


class BaseGenerateDocumentsForm(DsfrBaseForm, forms.Form):
    """Carries the context shared by every step of a generation wizard."""

    def __init__(self, *args, user, dotation, request, **kwargs):
        self.user = user
        self.dotation = dotation
        self.request = request
        super().__init__(*args, **kwargs)


class DocumentTypeFormMixin:
    """
    For the steps parameterized by what the run generates: one document type,
    or the arrêté + lettre pair.
    """

    def __init__(self, *args, document_type, **kwargs):
        super().__init__(*args, **kwargs)
        self.document_type = document_type

    @cached_property
    def selected_types(self) -> frozenset[str]:
        return SELECTED_TYPES_BY_CHOICE[self.document_type]


class BaseGenerateDocumentsLaunchForm(BaseGenerateDocumentsForm):
    """
    Validates the trigger button POST: the run applies either to the projets
    explicitly checked in the list, or to every projet matching the filters
    currently applied to it.

    Subclasses restrict them to the projets they can generate documents for.
    """

    ids = EnveloppeProjetMultipleChoiceField(
        queryset=EnveloppeProjet.objects.none(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ids"].queryset = (
            EnveloppeProjet.objects.programmees()
            .active()
            .visible_to_user(self.user)
            .filter(dotation=self.dotation)
            .select_related("projet")
        )

    def clean_ids(self):
        checked = self.cleaned_data.get("ids") or []
        if checked:
            queryset = EnveloppeProjet.objects.filter(pk__in=[dp.pk for dp in checked])
        else:
            queryset = ProgrammationFilters(
                data=self.request.GET, request=self.request
            ).qs
        ids = self.eligible_enveloppe_projets(queryset)
        if not ids:
            raise forms.ValidationError("Aucun projet à notifier.", code="no_projects")
        return ids

    def eligible_enveloppe_projets(
        self, queryset: EnveloppeProjetQuerySet
    ) -> EnveloppeProjetQuerySet:
        raise NotImplementedError


class GenerateAcceptedDocumentsLaunchForm(BaseGenerateDocumentsLaunchForm):
    def eligible_enveloppe_projets(self, queryset):
        return queryset.can_generate_accepted_documents()


class GenerateRefusLettersLaunchForm(BaseGenerateDocumentsLaunchForm):
    def eligible_enveloppe_projets(self, queryset):
        return queryset.can_generate_refus_documents()


class GenerateDocumentsTypeSelectionForm(BaseGenerateDocumentsForm):
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


class GenerateDocumentsModeleSelectionForm(
    DocumentTypeFormMixin, BaseGenerateDocumentsForm
):
    STRATEGY_CONSERVER = "conserver"
    STRATEGY_REMPLACER = "remplacer"

    def __init__(self, *args, enveloppe_projets, **kwargs):
        super().__init__(*args, **kwargs)
        self.enveloppe_projets = enveloppe_projets

        self.modele_entries = [
            ModeleSelectionEntry(self, t)
            for t in DOCUMENT_TYPE_DISPLAY_ORDER
            if t in self.selected_types
        ]

        # Conserver/Remplacer first: its "…ci-dessous" wording refers to the
        # model dropdowns rendered just below it.
        if self.entries_with_existing_docs:
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

        for entry in self.modele_entries:
            self.fields[entry.field_name] = entry.field

    @cached_property
    def _selected_nouns(self) -> list[str]:
        return [
            GENERATED_DOCUMENTS[t]._meta.verbose_name_plural.lower()
            for t in DOCUMENT_TYPE_DISPLAY_ORDER
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
        fem = ARRETE not in self.selected_types
        return f"Conserver {nouns} existant{pluralize(fem, 'es,s')}"

    @property
    def _remplacer_label(self) -> str:
        nouns = " et ".join(f"les {n}" for n in self._selected_nouns)
        fem = ARRETE not in self.selected_types
        # "toutes/tous" agrees with the first noun ("lettres" when present).
        quantifier = f"tou{pluralize(LETTRE in self.selected_types, 'tes,s')}"
        return (
            f"Remplacer {quantifier} {nouns} par "
            f"{pluralize(fem, 'celles,ceux')} "
            f"sélectionné{pluralize(fem, 'es,s')} ci-dessous"
        )

    @property
    def selected_modeles(self) -> list[ModeleDocument]:
        """The modeles chosen for the run, one per document type. Each one
        knows which document it generates, so the type isn't carried along."""
        return [self.cleaned_data[entry.field_name] for entry in self.modele_entries]

    @cached_property
    def entries_with_existing_docs(self) -> list["ModeleSelectionEntry"]:
        return [entry for entry in self.modele_entries if entry.existing_count]

    @cached_property
    def has_missing_modele(self) -> bool:
        return any(not entry.modeles for entry in self.modele_entries)


class ModeleSelectionEntry:
    """
    One row of GenerateDocumentsModeleSelectionForm's modele-selection step:
    the modele field for a single document type, its available modeles, and
    how many of the selected projets already have that document. The form
    (and the modele_selection.html template) loop over one entry per
    document type in `selected_types` instead of repeating a has_X/modeles_X/
    existing_X_count trio per type.
    """

    def __init__(self, form: GenerateDocumentsModeleSelectionForm, document_type: str):
        self.form = form
        self.document_type = document_type
        self.field_name = f"modele_{document_type}_id"

    @cached_property
    def modeles(self):
        perimetres = get_modele_perimetres(self.form.dotation, self.form.user.perimetre)
        return MODELES[self.document_type].objects.filter(
            dotation=self.form.dotation, perimetre__in=perimetres
        )

    @cached_property
    def existing_count(self) -> int:
        generated_document_class = MODELES[self.document_type].generated_document_class
        return generated_document_class.objects.filter(
            enveloppe_projet__in=self.form.enveloppe_projets
        ).count()

    @cached_property
    def field(self):
        return forms.ModelChoiceField(
            queryset=self.modeles,
            required=True,
            empty_label="Sélectionner un modèle",
            error_messages={
                "required": "Veuillez sélectionner un modèle.",
                "invalid_choice": "Modèle introuvable.",
            },
            label=self.modele_verbose_name,
        )

    @property
    def already_has_noun(self) -> str:
        document_class = GENERATED_DOCUMENTS[self.document_type]
        article = "une" if document_class.is_feminine else "un"
        short_name = GENERATED_DOCUMENTS[self.document_type].short_name
        return f"{article} {short_name.lower()}"

    @property
    def modele_verbose_name(self) -> str:
        return MODELES[self.document_type].verbose_name()


class GenerateDocumentsFormatForm(DocumentTypeFormMixin, BaseGenerateDocumentsForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["export_format"].choices = (
            self.EXPORT_FORMAT_CHOICES_BOTH
            if len(self.selected_types) > 1
            else self.EXPORT_FORMAT_CHOICES_SINGLE
        )


class GenerateDocumentsCreateForm(BaseGenerateDocumentsForm):
    """
    Save-action form for the wizard's final step. Receives data already cleaned
    and validated by the previous steps, through __init__ kwargs for the
    projets and through save() for the chosen modeles, and performs the
    document creation.
    """

    def __init__(self, *args, enveloppe_projets, **kwargs):
        super().__init__(*args, **kwargs)
        self.enveloppe_projets = enveloppe_projets
        self._pending_doc_actions = []

    def _log_doc_action(self, enveloppe_projet, document_class):
        self._pending_doc_actions.append(
            ProjetAction(
                projet=enveloppe_projet.projet,
                action_type=ProjetAction.TYPE_DOC_GENERATED,
                actor=self.user,
                source=ProjetAction.SOURCE_TURGOT,
                dotation=enveloppe_projet.dotation,
                document_name=document_class._meta.verbose_name.lower(),
                form_id=f"{type(self).__module__}.{type(self).__qualname__}",
            )
        )

    @transaction.atomic
    def save(self, *, modeles, overwrite_strategy):
        for modele in modeles:
            self._create_documents_of_type(modele, overwrite_strategy)

        ProjetAction.objects.bulk_create(self._pending_doc_actions)

        return list(
            EnveloppeProjet.objects.active().filter(pk__in=self.enveloppe_projets)
        )

    # replace_mentions_in_html() (every Mention in gsl.notification.utils.MENTIONS)
    # and _log_doc_action() walk these chains for every projet; without them
    # each hop is an extra N+1 query per document.
    ENVELOPPE_PROJETS_SELECT_RELATED = (
        "projet__dossier_ds__ds_demandeur__address__commune",
        "projet__dossier_ds__perimetre__departement",
    )

    def _create_documents_of_type(self, modele, overwrite_strategy):
        document_class = modele.generated_document_class

        if (
            overwrite_strategy
            == GenerateDocumentsModeleSelectionForm.STRATEGY_REMPLACER
        ):
            document_class.objects.filter(
                enveloppe_projet__in=self.enveloppe_projets
            ).delete()
            to_create = self.enveloppe_projets.select_related(
                *self.ENVELOPPE_PROJETS_SELECT_RELATED
            )
        else:
            to_create = (
                EnveloppeProjet.objects.active()
                .filter(pk__in=self.enveloppe_projets)
                .exclude(pk__in=document_class.objects.values("enveloppe_projet_id"))
                .select_related(*self.ENVELOPPE_PROJETS_SELECT_RELATED)
            )

        for enveloppe_projet in to_create:
            document_class(
                enveloppe_projet=enveloppe_projet,
                modele=modele,
                created_by=self.user,
                content=replace_mentions_in_html(modele.content, enveloppe_projet),
            ).save()
            self._log_doc_action(enveloppe_projet, document_class)
