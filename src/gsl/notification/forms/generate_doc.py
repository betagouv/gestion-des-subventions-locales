from django import forms
from django.db import transaction
from dsfr.forms import DsfrBaseForm

from gsl.notification.models import GeneratedDocument, ModeleDocument
from gsl.notification.utils import (
    get_modele_perimetres,
    log_generated_document_action,
    replace_mentions_in_html,
)
from gsl.projet.constants import ProjetStatus


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
        self.treated_enveloppe_projets = list(
            projet.enveloppeprojet_set.filter(status__in=ProjetStatus.FINAL).order_by(
                "enveloppe__dotation"
            )
        )

        self.dotation_fields = {
            ep.dotation: {
                "enveloppe_projet": ep,
                "fields": DOTATION_STATUS_TO_DOCUMENT_FIELDS_CLASS[ep.status](
                    self, ep
                ).build(),
            }
            for ep in self.treated_enveloppe_projets
        }

    def clean(self):
        cleaned_data = super().clean()
        for ep in self.treated_enveloppe_projets:
            for fields in self.dotation_fields[ep.dotation]["fields"].values():
                modele_name = fields["modele"].name
                skip_name = fields["skip"].name
                if not cleaned_data.get(skip_name) and not cleaned_data.get(
                    modele_name
                ):
                    self.add_error(
                        modele_name,
                        f"Sélectionnez un modèle ou cochez la case pour ne pas générer {fields['document_type'].article_name}.",
                    )
        return cleaned_data

    @transaction.atomic
    def save(self):
        with_qr_code = not self.cleaned_data["hide_qr_code"]
        documents = []
        for ep in self.treated_enveloppe_projets:
            for fields in self.dotation_fields[ep.dotation]["fields"].values():
                if not self.cleaned_data[fields["skip"].name]:
                    documents.append(
                        self._generate_document(
                            ep,
                            self.cleaned_data[fields["modele"].name],
                            with_qr_code,
                        )
                    )
        return documents

    def _generate_document(self, enveloppe_projet, modele, with_qr_code):
        existing = enveloppe_projet.generated_document(modele.type)
        if existing:
            existing.delete()

        document = GeneratedDocument(
            type=modele.type,
            enveloppe_projet=enveloppe_projet,
            modele=modele,
            created_by=self.user,
            content=replace_mentions_in_html(modele.content, enveloppe_projet),
            with_qr_code=with_qr_code,
        )
        document.save()
        log_generated_document_action(
            self.user, enveloppe_projet, document, is_creating=existing is None
        )
        return document


class DotationDocumentFields:
    """
    The "widget" for one dotation on the generate-documents card: a modele
    selector + skip checkbox for the arrêté, and the same pair for the
    lettre. Registers its 4 fields on the form and returns them grouped for
    template consumption.
    """

    document_types: tuple[GeneratedDocument.Type, ...] = ()

    def __init__(self, form: GenerateDotationsDocumentsForm, enveloppe_projet):
        self.form = form
        self.dotation = enveloppe_projet.dotation
        self.enveloppe_projet = enveloppe_projet

    def build(self) -> dict:
        widget_fields = {}

        perimetres = get_modele_perimetres(self.dotation, self.form.user.perimetre)
        if not perimetres:  # if user regional and DETR => no field in widget !
            return {}

        for document_type in self.document_types:
            modele_bound_field = self._add_modele_field(document_type, perimetres)
            has_modele_document = modele_bound_field.field.queryset.exists()
            skip_bound_field = self._add_skip_field(
                document_type,
                disabled=not has_modele_document,
            )
            widget_fields[document_type] = {
                "modele": modele_bound_field,
                "has_modele": has_modele_document,
                "skip": skip_bound_field,
                "document_type": document_type,
            }

        return widget_fields

    def _add_modele_field(self, document_type, perimetres):
        name = f"modele_{document_type}_{self.dotation}"
        existing_document = self.enveloppe_projet.generated_document(document_type)
        self.form.fields[name] = forms.ModelChoiceField(
            queryset=ModeleDocument.objects.filter(
                type=document_type, dotation=self.dotation, perimetre__in=perimetres
            ),
            required=False,
            empty_label="Sélectionner un modèle",
            label=document_type.modele_verbose_name.capitalize(),
            initial=existing_document.modele if existing_document else None,
            widget=forms.Select(attrs={"data-skip-document-toggle-target": "select"}),
        )
        return self.form[name]

    def _add_skip_field(self, document_type, disabled: bool):
        # disabled=True both forces cleaned_data to the initial value (True),
        # ignoring whatever is posted, and renders the checkbox non-interactive.
        name = f"skip_{document_type}_{self.dotation}"
        self.form.fields[name] = forms.BooleanField(
            required=False,
            label=f"Ne pas générer {document_type.article_name}",
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
    document_types = (GeneratedDocument.Type.ARRETE, GeneratedDocument.Type.LETTRE)


class RefusedOrDismissedDotationDocumentFields(DotationDocumentFields):
    document_types = (GeneratedDocument.Type.LETTRE_REFUS,)


DOTATION_STATUS_TO_DOCUMENT_FIELDS_CLASS = {
    ProjetStatus.ACCEPTED: AcceptedDotationDocumentFields,
    ProjetStatus.REFUSED: RefusedOrDismissedDotationDocumentFields,
    ProjetStatus.DISMISSED: RefusedOrDismissedDotationDocumentFields,
}
