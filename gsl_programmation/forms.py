from django import forms

from gsl_programmation.models import Arrete


class ArreteForm(forms.ModelForm):
    class Meta:
        model = Arrete
        fields = ["programmation_projet", "numero", "date", "document", "content"]
        widgets = {
            "content": forms.HiddenInput(),  # rempli en JSON par TipTap
        }
