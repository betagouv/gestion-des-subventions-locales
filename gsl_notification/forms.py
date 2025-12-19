from django import forms
from django.db import transaction
from django.forms import ModelForm
from django.utils import timezone
from dsfr.forms import DsfrBaseForm

from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService
from gsl_notification.models import (
    Annexe,
    Arrete,
    ArreteEtLettreSignes,
    LettreNotification,
    ModeleDocument,
)
from gsl_notification.utils import merge_documents_into_pdf
from gsl_programmation.models import ProgrammationProjet
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


class BaseChooseDocumentTypeForm(DsfrBaseForm, ModelForm):
    document = forms.ChoiceField(
        widget=RadioSelect,
        required=True,
        choices=[],
        label="Type de document",
    )

    def clean_document(self):
        doc_type, dotation = self.cleaned_data["document"].split("-")
        return {
            "type": doc_type,
            "dotation": dotation,
        }


class ChooseDocumentTypeForGenerationForm(BaseChooseDocumentTypeForm):
    def __init__(self, *args, **kwargs):
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
            for dp in self.instance.dotationprojet_set.filter(
                status=PROJET_STATUS_ACCEPTED
            )
        ]

    class Meta:
        model = Projet
        fields = ()


class ChooseDocumentTypeForUploadForm(BaseChooseDocumentTypeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        for dp in self.instance.dotationprojet_set.filter(
            status=PROJET_STATUS_ACCEPTED
        ):
            # Check if ProgrammationProjet exists for this dotation
            try:
                prog_projet = ProgrammationProjet.objects.get(
                    dotation_projet=dp, dotation_projet__projet=self.instance
                )
                # ArreteEtLettreSignes (disable if already exists)
                existing_arrete = hasattr(prog_projet, "arrete_et_lettre_signes")

                choices.append(
                    (
                        (
                            ""
                            if existing_arrete
                            else f"arrete_et_lettre_signes-{dp.dotation}"
                        ),
                        f"Arrêté et lettre signés {dp.dotation.upper()}",
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

    class Meta:
        model = Projet
        fields = ()


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
        model = ArreteEtLettreSignes
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
                *ArreteEtLettreSignes.objects.filter(
                    programmation_projet__dotation_projet__projet=self.instance
                ),
                *self.cleaned_data["annexes"],
            ]
        )

        # Dossier was recently refreshed DN
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
        if self.instance.dossier_ds.ds_state == Dossier.STATE_EN_CONSTRUCTION:
            ds = DsService()
            ds.passer_en_instruction(
                dossier=self.instance.dossier_ds, user=user
            )
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
