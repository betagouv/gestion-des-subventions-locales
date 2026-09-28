from django import forms
from django.db import transaction
from dsfr.forms import DsfrBaseForm

from gsl.notification.models import MODELES
from gsl.notification.utils import (
    get_modele_perimetres,
    log_generated_document_action,
    replace_mentions_in_html,
)
from gsl.projet.constants import ARRETE, LETTRE, LETTRE_REFUS, ProjetStatus


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
                "dotation"
            )
        )

        self.dotation_fields = {
            dp.dotation: {
                "enveloppe_projet": dp,
                "fields": DOTATION_STATUS_TO_DOCUMENT_FIELDS_CLASS[dp.status](
                    self, dp
                ).build(),
            }
            for dp in self.treated_enveloppe_projets
        }

    def clean(self):
        cleaned_data = super().clean()
        for dp in self.treated_enveloppe_projets:
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
        for dp in self.treated_enveloppe_projets:
            for fields in self.dotation_fields[dp.dotation]["fields"].values():
                if not self.cleaned_data[fields["skip"].name]:
                    documents.append(
                        self._generate_document(
                            fields["modele_class"],
                            dp,
                            self.cleaned_data[fields["modele"].name],
                            with_qr_code,
                        )
                    )
        return documents

    def _generate_document(self, modele_class, enveloppe_projet, modele, with_qr_code):
        document_class = modele_class.generated_document_class
        is_creating = not hasattr(enveloppe_projet, modele_class.type)
        if not is_creating:
            getattr(enveloppe_projet, modele_class.type).delete()

        document = document_class(
            enveloppe_projet=enveloppe_projet,
            modele=modele,
            created_by=self.user,
            content=replace_mentions_in_html(modele.content, enveloppe_projet),
            with_qr_code=with_qr_code,
        )
        document.save()
        log_generated_document_action(
            self.user, enveloppe_projet, document_class, is_creating
        )
        return document


class DotationDocumentFields:
    """
    The "widget" for one dotation on the generate-documents card: a modele
    selector + skip checkbox for the arrêté, and the same pair for the
    lettre. Registers its 4 fields on the form and returns them grouped for
    template consumption.
    """

    modeles = []

    def __init__(self, form: GenerateDotationsDocumentsForm, enveloppe_projet):
        self.form = form
        self.dotation = enveloppe_projet.dotation
        self.enveloppe_projet = enveloppe_projet

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
        existing_document = getattr(self.enveloppe_projet, modele_class.type, None)
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
    ProjetStatus.ACCEPTED: AcceptedDotationDocumentFields,
    ProjetStatus.REFUSED: RefusedOrDismissedDotationDocumentFields,
    ProjetStatus.DISMISSED: RefusedOrDismissedDotationDocumentFields,
}
