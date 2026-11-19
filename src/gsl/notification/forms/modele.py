from django import forms
from dsfr.forms import DsfrBaseForm

from gsl.notification.models import ModeleDocument


class ModeleDocumentStepZeroForm(DsfrBaseForm):
    type = forms.ChoiceField(
        label="Type de document",
        choices=ModeleDocument._meta.get_field("type").choices,
        widget=forms.RadioSelect,
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
