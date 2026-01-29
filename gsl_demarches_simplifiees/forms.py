from django import forms
from django.forms.widgets import CheckboxSelectMultiple
from dsfr.forms import DsfrBaseForm

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import DOTATION_CHOICES
from gsl_projet.services.dotation_projet_services import DotationProjetService


class DotationFormField(forms.MultipleChoiceField):
    """
    Widget for overriding demande_dispositif_sollicite, which is a CharField
    for legacy reason, but should be a ArrayField or MultipleChoiceField.
    """

    widget = CheckboxSelectMultiple

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, choices=DOTATION_CHOICES, **kwargs)

    def prepare_value(self, value):
        list_value = []
        for v in self.choices:
            if v[0] in value:
                list_value.append(v[0])
        return list_value


class DossierReporteSansPieceForm(forms.ModelForm, DsfrBaseForm):
    demande_dispositif_sollicite = DotationFormField(
        required=True, label="Dispositif de financement sollicité"
    )
    finance_cout_total = forms.DecimalField(
        required=True, label="Coût total de l'opération (en euros HT)"
    )
    demande_montant = forms.DecimalField(
        required=True, label="Montant de l'aide demandée"
    )

    def save(self, commit=True):
        instance = super().save(commit=commit)
        service = DotationProjetService()
        service.create_or_update_dotation_projet_from_projet(instance.projet)
        return instance

    class Meta:
        model = Dossier
        fields = [
            "demande_dispositif_sollicite",
            "finance_cout_total",
            "demande_montant",
        ]
        widgets = {
            "finance_cout_total": forms.TextInput(attrs={"inputmode": "numeric"}),
            "demande_montant": forms.TextInput(attrs={"inputmode": "numeric"}),
        }
