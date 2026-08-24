import json
import os
from functools import cached_property

from django import forms
from django.conf import settings
from django.db import transaction
from django.template.defaultfilters import pluralize
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import get_valid_filename
from dsfr.forms import DsfrBaseForm

from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService
from gsl_historique.models import ProjetAction
from gsl_notification.models import (
    GENERATED_DOCUMENTS,
    MODELES,
    UPLOADED_DOCUMENTS,
    Arrete,
    DocumentImportJob,
    ExportJob,
    LettreNotification,
    LettreRefus,
    ModeleArrete,
    ModeleDocument,
)
from gsl_notification.tasks import run_document_import_job
from gsl_notification.utils import (
    get_modele_perimetres,
    log_generated_document_action,
    merge_documents_into_pdf,
    replace_mentions_in_html,
)
from gsl_notification.validators import document_file_validator
from gsl_programmation.models import ProgrammationProjet, ProgrammationProjetQuerySet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import (
    ARRETE,
    DOTATIONS,
    LETTRE,
    LETTRE_REFUS,
    PROJET_FINAL_STATUSES,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import Projet


class PresignedUploadForm(forms.Form):
    filename = forms.CharField(error_messages={"required": "Nom de fichier manquant."})

    def clean_filename(self):
        sanitized = get_valid_filename(self.cleaned_data["filename"].strip())
        if not sanitized.lower().endswith(".pdf"):
            raise forms.ValidationError("Seuls les fichiers PDF sont acceptés.")
        return sanitized


class S3KeysField(forms.Field):
    """JSON-encoded list of S3 keys, filtered to the temp import prefix."""

    default_error_messages = {
        "invalid": "Requête invalide.",
        "required": "Aucun fichier à importer.",
    }

    def to_python(self, value):
        if value in self.empty_values:
            return []
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        if not isinstance(raw, list):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        # Never trust the client with an arbitrary bucket key.
        return [
            key
            for key in raw
            if isinstance(key, str) and key.startswith(DocumentImportJob.TEMP_S3_PREFIX)
        ]


class ImportJobStartForm(forms.Form):
    s3_keys = S3KeysField()
    remove_qr_code = forms.BooleanField(required=False)

    def save(self, user):
        job = DocumentImportJob.objects.create(
            created_by=user,
            s3_keys=self.cleaned_data["s3_keys"],
            remove_qr_code=self.cleaned_data["remove_qr_code"],
        )
        # Tâche longue, déclenchée par un agent qui attend le résultat : priorité
        # normale (défaut). La passer en haute la ferait bloquer le worker unique
        # devant les tâches courtes non bloquantes.
        run_document_import_job.delay(str(job.pk))
        return job


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


class ChooseDocumentTypeForMultipleGenerationForm(BaseChooseDocumentTypeForm):
    pass


class ChooseDocumentTypeForUploadForm(BaseChooseDocumentTypeForm):
    def __init__(self, *args, instance, **kwargs):
        # Not a ModelForm, but we get instance from the view which is an UpdateView.
        super().__init__(*args, **kwargs)
        self.instance = instance
        choices = []
        for dp in instance.dotationprojet_set.filter(status__in=PROJET_FINAL_STATUSES):
            try:
                prog_projet = dp.programmation_projet
            except ProgrammationProjet.DoesNotExist:
                continue
            for model in UPLOADED_DOCUMENTS.values():
                if dp.status not in model.upload_statuses:
                    continue
                can_upload = model.can_upload(prog_projet)
                choices.append(
                    (
                        (f"{model.document_type}-{dp.dotation}" if can_upload else ""),
                        f"{model.verbose_name()} {dp.dotation.upper()}",
                    )
                )

        self.fields["document"].choices = choices

    def clean_document(self):
        doc_type, dotation = self.cleaned_data["document"].split("-")
        return {
            "type": doc_type,
            "dotation": dotation,
        }


class DotationDocumentFields:
    """
    The "widget" for one dotation on the generate-documents card: a modele
    selector + skip checkbox for the arrêté, and the same pair for the
    lettre. Registers its 4 fields on the form and returns them grouped for
    template consumption.
    """

    modeles = []

    def __init__(self, form: "GenerateDotationsDocumentsForm", dotation_projet):
        self.form = form
        self.dotation = dotation_projet.dotation
        self.dotation_projet = dotation_projet

    def build(self) -> dict:
        widget_fields = {}

        perimetres = get_modele_perimetres(self.dotation, self.form.user.perimetre)
        for modele_class in self.modeles:
            modele_fields = {}
            modele_bound_field = self._add_modele_field(
                modele_class,
                perimetres,
            )
            has_modele_document = modele_bound_field.field.queryset.exists()
            skip_bound_field = self._add_skip_field(
                modele_class,
                disabled=not has_modele_document,
            )

            modele_fields["modele"] = modele_bound_field
            modele_fields["has_modele"] = has_modele_document
            modele_fields["skip"] = skip_bound_field
            modele_fields["modele_class"] = modele_class
            widget_fields[modele_class.type] = modele_fields

        return widget_fields

    def _add_modele_field(self, modele_class, perimetres):
        name = f"modele_{modele_class.type}_{self.dotation}"
        existing_document = getattr(
            self.dotation_projet.programmation_projet, modele_class.type, None
        )
        self.form.fields[name] = forms.ModelChoiceField(
            queryset=modele_class.objects.filter(
                dotation=self.dotation, perimetre__in=perimetres
            ),
            required=False,
            empty_label="Sélectionner un modèle",
            label=modele_class.verbose_name().capitalize(),
            initial=existing_document.modele if existing_document else None,
            widget=forms.Select(attrs={"data-skip-document-toggle-target": "select"}),
        )
        return self.form[name]

    def _add_skip_field(self, modele_class, disabled: bool):
        # disabled=True both forces cleaned_data to the initial value (True),
        # ignoring whatever is posted, and renders the checkbox non-interactive.
        name = f"skip_{modele_class.type}_{self.dotation}"
        self.form.fields[name] = forms.BooleanField(
            required=False,
            label=f"Ne pas générer {modele_class.article_name}",
            initial=disabled,
            disabled=disabled,
            widget=forms.CheckboxInput(
                attrs={
                    "data-skip-document-toggle-target": "checkbox",
                    "data-action": "change->skip-document-toggle#toggle",
                }
            ),
        )
        return self.form[name]


class AcceptedDotationDocumentFields(DotationDocumentFields):
    modeles = [MODELES[modele] for modele in [ARRETE, LETTRE]]


class RefusedOrDismissedDotationDocumentFields(DotationDocumentFields):
    modeles = [MODELES[LETTRE_REFUS]]


DOTATION_STATUS_TO_DOCUMENT_FIELDS_CLASS = {
    PROJET_STATUS_ACCEPTED: AcceptedDotationDocumentFields,
    PROJET_STATUS_REFUSED: RefusedOrDismissedDotationDocumentFields,
    PROJET_STATUS_DISMISSED: RefusedOrDismissedDotationDocumentFields,
}


class GenerateDotationsDocumentsForm(DsfrBaseForm):
    """
    Inline "1 - Générer" card on the notifications tab: one box per accepted
    dotation, each with a modele selector + skip checkbox for the arrêté and
    for the lettre. Submitting (re)generates every non-skipped document,
    deleting and recreating it if it already exists.
    """

    hide_qr_code = forms.BooleanField(
        required=False,
        label="Masquer le QR code de suivi",
        help_text=(
            "Le QR code permet de rattacher automatiquement un document signé "
            "scanné au bon projet. Il est retiré lors de l’import."
        ),
    )

    def __init__(self, *args, projet, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.treated_dotation_projets = list(
            projet.dotationprojet_set.filter(status__in=PROJET_FINAL_STATUSES).order_by(
                "dotation"
            )
        )

        self.dotation_fields = {
            dp.dotation: {
                "dotation_projet": dp,
                "fields": DOTATION_STATUS_TO_DOCUMENT_FIELDS_CLASS[dp.status](
                    self, dp
                ).build(),
            }
            for dp in self.treated_dotation_projets
        }

    def clean(self):
        cleaned_data = super().clean()
        for dp in self.treated_dotation_projets:
            for fields in self.dotation_fields[dp.dotation]["fields"].values():
                modele_name = fields["modele"].name
                skip_name = fields["skip"].name
                if not cleaned_data.get(skip_name) and not cleaned_data.get(
                    modele_name
                ):
                    self.add_error(
                        modele_name,
                        f"Sélectionnez un modèle ou cochez la case pour ne pas générer {fields['modele_class'].article_name}.",
                    )
        return cleaned_data

    @transaction.atomic
    def save(self):
        with_qr_code = not self.cleaned_data["hide_qr_code"]
        documents = []
        for dp in self.treated_dotation_projets:
            for fields in self.dotation_fields[dp.dotation]["fields"].values():
                if not self.cleaned_data[fields["skip"].name]:
                    documents.append(
                        self._generate_document(
                            fields["modele_class"],
                            dp.programmation_projet,
                            self.cleaned_data[fields["modele"].name],
                            with_qr_code,
                        )
                    )
        return documents

    def _generate_document(
        self, modele_class, programmation_projet, modele, with_qr_code
    ):
        document_class = modele_class.generated_document_class
        is_creating = not hasattr(programmation_projet, modele_class.type)
        if not is_creating:
            getattr(programmation_projet, modele_class.type).delete()

        document = document_class(
            programmation_projet=programmation_projet,
            modele=modele,
            created_by=self.user,
            content=replace_mentions_in_html(modele.content, programmation_projet),
            with_qr_code=with_qr_code,
        )
        document.save()
        log_generated_document_action(
            self.user, programmation_projet, document_class, is_creating
        )
        return document


class ArreteForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Arrete
        fields = (
            "content",
            "created_by",
            "programmation_projet",
            "modele",
            "with_qr_code",
        )


class LettreNotificationForm(ArreteForm):
    class Meta(ArreteForm.Meta):
        model = LettreNotification


class LettreRefusForm(ArreteForm):
    class Meta(ArreteForm.Meta):
        model = LettreRefus


class ModeleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return format_html(
            "{}<span class='fr-hint-text'>{}</span>", obj.name, obj.description
        )


class ChoixModeleForm(DsfrBaseForm):
    modele = ModeleChoiceField(
        queryset=ModeleArrete.objects.none(),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Modèle",
    )

    def __init__(self, *args, queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modele"].queryset = queryset

    @property
    def has_modele_choices(self):
        return self.fields["modele"].queryset.exists()


GENERATED_DOCUMENT_TO_FORM = {
    LETTRE: LettreNotificationForm,
    ARRETE: ArreteForm,
    LETTRE_REFUS: LettreRefusForm,
}


class UploadedDocumentForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        fields = ("file", "created_by", "programmation_projet")


UPLOADED_DOCUMENT_FORMS = {
    document_type: forms.modelform_factory(
        model, form=UploadedDocumentForm, fields=UploadedDocumentForm.Meta.fields
    )
    for document_type, model in UPLOADED_DOCUMENTS.items()
}


class ModeleDocumentStepZeroForm(DsfrBaseForm):
    TYPE_CHOICES = tuple((type_, klass.type_label) for type_, klass in MODELES.items())
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


class NotificationMessageForm(DsfrBaseForm, forms.ModelForm):
    message = forms.CharField(
        label="Message de notification",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    class Meta:
        model = Projet
        fields = ()

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.dotationprojet_set.without_signed_document().exists():
            raise forms.ValidationError(
                "Impossible d'envoyer la notification : il manque des documents "
                "signés obligatoires."
            )
        return cleaned_data

    def save(self, user):
        documents = self.instance.imported_documents
        filename = self._notification_filename(documents)
        justificatif_file = merge_documents_into_pdf(documents, filename=filename)

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
                motivation=self.cleaned_data.get("message", ""),
                document=justificatif_file,
            )
            ProjetAction.objects.create(
                projet=self.instance,
                action_type=ProjetAction.TYPE_NOTIFIED,
                actor=user,
                source=ProjetAction.SOURCE_TURGOT,
                form_id=f"{type(self).__module__}.{type(self).__qualname__}",
            )

            return self.instance

    def _notification_filename(self, documents):
        accepted_dotations = set(
            self.instance.dotationprojet_set.filter(
                status=PROJET_STATUS_ACCEPTED
            ).values_list("dotation", flat=True)
        )
        if len(accepted_dotations) <= 1:
            return os.path.splitext(documents[0].name)[0] + ".pdf"
        ordered = [d for d in DOTATIONS if d in accepted_dotations]
        ds_number = self.instance.dossier_ds.ds_number
        return f"Notification {ds_number} {'-'.join(ordered)}.pdf"


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
        projet = self.instance
        dossier = projet.dossier_ds
        ds = DsService()

        # Dossier was recently refreshed DN
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
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
            form_id=f"{type(self).__module__}.{type(self).__qualname__}",
        )
        return projet


# -- Multi-projet document generation modal forms --

ARRETE_ET_LETTRE = ExportJob.DOCUMENT_TYPE_ARRETE_ET_LETTRE

EXPORT_FORMAT_ONE_PDF_PER_DOC = ExportJob.EXPORT_FORMAT_ONE_PDF_PER_DOC
EXPORT_FORMAT_ONE_PDF_ALL = ExportJob.EXPORT_FORMAT_ONE_PDF_ALL
EXPORT_FORMAT_ONE_PDF_PER_PROJECT = ExportJob.EXPORT_FORMAT_ONE_PDF_PER_PROJECT
EXPORT_FORMAT_ONE_PDF_ALL_GROUPED = ExportJob.EXPORT_FORMAT_ONE_PDF_ALL_GROUPED


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

    ids = ProgrammationProjetMultipleChoiceField(
        queryset=ProgrammationProjet.objects.none(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ids"].queryset = (
            ProgrammationProjet.objects.active()
            .visible_to_user(self.user)
            .filter(dotation_projet__dotation=self.dotation)
            .select_related("dotation_projet__projet")
        )

    def clean_ids(self):
        checked = self.cleaned_data.get("ids") or []
        if checked:
            queryset = ProgrammationProjet.objects.filter(
                pk__in=[pp.pk for pp in checked]
            )
        else:
            queryset = ProgrammationProjetFilters(
                data=self.request.GET, request=self.request
            ).qs
        ids = self.eligible_programmation_projets(queryset)
        if not ids:
            raise forms.ValidationError("Aucun projet à notifier.", code="no_projects")
        return ids

    def eligible_programmation_projets(
        self, queryset: ProgrammationProjetQuerySet
    ) -> ProgrammationProjetQuerySet:
        raise NotImplementedError


class GenerateAcceptedDocumentsLaunchForm(BaseGenerateDocumentsLaunchForm):
    def eligible_programmation_projets(self, queryset):
        return queryset.can_generate_accepted_documents()


class GenerateRefusLettersLaunchForm(BaseGenerateDocumentsLaunchForm):
    def eligible_programmation_projets(self, queryset):
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

    def __init__(self, *args, programmation_projets, **kwargs):
        super().__init__(*args, **kwargs)
        self.programmation_projets = programmation_projets

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
    (and the modal_modele_selection.html template) loop over one entry per
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
            programmation_projet__in=self.form.programmation_projets
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

    def __init__(self, *args, programmation_projets, **kwargs):
        super().__init__(*args, **kwargs)
        self.programmation_projets = programmation_projets
        self._pending_doc_actions = []

    def _log_doc_action(self, pp, document_class):
        self._pending_doc_actions.append(
            ProjetAction(
                projet=pp.dotation_projet.projet,
                action_type=ProjetAction.TYPE_DOC_GENERATED,
                actor=self.user,
                source=ProjetAction.SOURCE_TURGOT,
                dotation=pp.dotation_projet.dotation,
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
            ProgrammationProjet.objects.active().filter(
                pk__in=self.programmation_projets
            )
        )

    # replace_mentions_in_html() (every Mention in gsl_notification.utils.MENTIONS)
    # and _log_doc_action() walk these chains for every projet; without them
    # each hop is an extra N+1 query per document.
    PPS_TO_CREATE_SELECT_RELATED = (
        "dotation_projet__projet__dossier_ds__ds_demandeur__address__commune",
        "dotation_projet__projet__dossier_ds__perimetre__departement",
    )

    def _create_documents_of_type(self, modele, overwrite_strategy):
        document_class = modele.generated_document_class

        if (
            overwrite_strategy
            == GenerateDocumentsModeleSelectionForm.STRATEGY_REMPLACER
        ):
            document_class.objects.filter(
                programmation_projet__in=self.programmation_projets
            ).delete()
            pps_to_create = self.programmation_projets.select_related(
                *self.PPS_TO_CREATE_SELECT_RELATED
            )
        else:
            pps_to_create = (
                ProgrammationProjet.objects.active()
                .filter(pk__in=self.programmation_projets)
                .exclude(
                    pk__in=document_class.objects.values("programmation_projet_id")
                )
                .select_related(*self.PPS_TO_CREATE_SELECT_RELATED)
            )

        for pp in pps_to_create:
            document_class(
                programmation_projet=pp,
                modele=modele,
                created_by=self.user,
                content=replace_mentions_in_html(modele.content, pp),
            ).save()
            self._log_doc_action(pp, document_class)
