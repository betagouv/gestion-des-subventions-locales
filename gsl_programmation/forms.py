from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe


class EnveloppeForm(DsfrBaseForm, ModelForm):
    def __init__(self, *args, perimetres_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["perimetre"].queryset = perimetres_qs

    def clean(self):
        perimetre: Perimetre = self.cleaned_data.get("perimetre")
        if perimetre.parent is not None:
            self.instance.deleguee_by = Enveloppe.objects.filter(
                dotation=self.cleaned_data.get("dotation"), perimetre=perimetre.parent
            ).first()

        if self.instance.deleguee_by is not None:
            self.instance.annee = self.instance.deleguee_by.annee
        else:
            self.instance.annee = (
                Enveloppe.objects.order_by("-annee")
                .values_list("annee", flat=True)
                .first()
            )
        self.instance.validate_constraints()
        return super().clean()

    class Meta:
        model = Enveloppe
        fields = (
            "dotation",
            "perimetre",
            "montant",
        )
