from django.core.exceptions import ValidationError
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe
from gsl_projet.constants import DOTATION_DSIL


class SubEnveloppeCreateForm(DsfrBaseForm, ModelForm):
    def __init__(self, *args, user_perimetre: Perimetre, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_perimetre = user_perimetre
        if self.user_perimetre.type == Perimetre.TYPE_REGION:
            self.fields["dotation"].widget = self.fields["dotation"].hidden_widget()
            self.fields["dotation"].choices = ((DOTATION_DSIL, DOTATION_DSIL),)
            self.fields["dotation"].initial = DOTATION_DSIL
        self.fields["perimetre"].queryset = Perimetre.objects.filter(
            pk__in=(
                p.id
                for p in (
                    user_perimetre,
                    *user_perimetre.children(max_depth=1),
                )
            ),
            # Une sous-enveloppe ne peut pas être déléguée si elle est régionale
            departement__isnull=False,
        )

    def clean(self):
        perimetre: Perimetre = self.cleaned_data.get("perimetre")
        self.instance.deleguee_by = (
            Enveloppe.objects.filter(
                dotation=self.cleaned_data.get("dotation"), perimetre=perimetre.parent
            )
            .order_by("-annee")
            .first()
        )
        if self.instance.deleguee_by is None:
            # We need something to trigger model validation errors
            self.instance.annee = 1

            raise ValidationError(
                "L'enveloppe doit être une sous-enveloppe d'une enveloppe existante."
            )

        self.instance.annee = self.instance.deleguee_by.annee
        return super().clean()

    def _get_validation_exclusions(self):
        """
        We force inclusion of all fields in validation because we want to test multiple fields unicity.

        TODO: Tell Django dev this should be a public method
        """
        return set("annee")

    class Meta:
        model = Enveloppe
        fields = (
            "dotation",
            "perimetre",
            "montant",
        )


class SubEnveloppeUpdateForm(DsfrBaseForm, ModelForm):
    class Meta:
        model = Enveloppe
        fields = ("montant",)
