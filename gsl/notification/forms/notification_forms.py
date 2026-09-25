from django import forms
from dsfr.forms import DsfrBaseForm

from gsl.projet.constants import ProjetStatus
from gsl.projet.models import Projet


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.status != ProjetStatus.ACCEPTED:
            self.fields["message"].required = True

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.enveloppeprojet_set.without_signed_document().exists():
            raise forms.ValidationError(
                "Impossible d'envoyer la notification : il manque des documents "
                "signés obligatoires."
            )
        return cleaned_data

    def save(self, user):
        self.instance.notify(user, motivation=self.cleaned_data.get("message", ""))
        return self.instance
