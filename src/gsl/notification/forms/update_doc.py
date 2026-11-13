from django import forms
from django.utils.html import format_html
from dsfr.forms import DsfrBaseForm

from gsl.notification.models import GeneratedDocument, ModeleDocument


class GeneratedDocumentForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = GeneratedDocument
        fields = (
            "content",
            "created_by",
            "enveloppe_projet",
            "modele",
            "with_qr_code",
        )


class ModeleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return format_html(
            "{}<span class='fr-hint-text'>{}</span>", obj.name, obj.description
        )


class ChoixModeleForm(DsfrBaseForm):
    modele = ModeleChoiceField(
        queryset=ModeleDocument.objects.none(),
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
