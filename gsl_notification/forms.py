from django import forms
from django.db import transaction
from django.utils import timezone
from dsfr.forms import DsfrBaseForm

from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_notification.models import (
    Annexe,
    Arrete,
    ArreteEtLettreSignes,
    LettreNotification,
    ModeleDocument,
)
from gsl_notification.utils import merge_documents_into_pdf
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import ARRETE, LETTRE


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


class NotificationMessageForm(DsfrBaseForm, forms.Form):
    annexes = AnnexeChoiceField(
        widget=forms.CheckboxSelectMultiple,
        queryset=Annexe.objects.none(),
        label="Pièces jointes",
    )
    justification = forms.CharField(
        label="Justification de l'acceptation du dossier (facultatif)",
        required=False,
        widget=forms.Textarea,
    )

    def save(self, instructeur_id):
        justificatif_file = merge_documents_into_pdf(
            [
                self.programmation_projet.arrete_et_lettre_signes,
                *self.cleaned_data["annexes"],
            ]
        )

        with transaction.atomic():
            self.programmation_projet.notified_at = timezone.now()
            self.programmation_projet.save()
            DsMutator().dossier_accepter(
                self.programmation_projet.dossier,
                instructeur_id,
                motivation=self.cleaned_data.get("justification", ""),
                document=justificatif_file,
            )

    def __init__(self, *args, instance: ProgrammationProjet, **kwargs):
        super().__init__(*args, **kwargs)
        self.programmation_projet = instance
        self.fields["annexes"].queryset = self.programmation_projet.annexes.all()
