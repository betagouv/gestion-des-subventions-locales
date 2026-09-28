from django import forms
from django.utils.html import format_html
from dsfr.forms import DsfrBaseForm

from gsl.notification.models import (
    Arrete,
    LettreNotification,
    LettreRefus,
    ModeleArrete,
)
from gsl.projet.constants import ARRETE, LETTRE, LETTRE_REFUS


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
            "enveloppe_projet",
            "modele",
            "with_qr_code",
        )


class LettreNotificationForm(ArreteForm):
    class Meta(ArreteForm.Meta):
        model = LettreNotification


class LettreRefusForm(ArreteForm):
    class Meta(ArreteForm.Meta):
        model = LettreRefus


GENERATED_DOCUMENT_TO_FORM = {
    LETTRE: LettreNotificationForm,
    ARRETE: ArreteForm,
    LETTRE_REFUS: LettreRefusForm,
}


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
