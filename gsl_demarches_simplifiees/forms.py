from itertools import groupby

from django import forms
from django.forms.widgets import CheckboxSelectMultiple
from dsfr.forms import DsfrBaseForm

from gsl_demarches_simplifiees.models import CategorieDetr, CategorieDsil, Dossier
from gsl_projet.constants import DOTATION_CHOICES, DOTATION_DETR, DOTATION_DSIL
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        demarche = self.instance.ds_demarche

        self.fields["demande_categorie_dsil"].queryset = CategorieDsil.objects.filter(
            demarche=demarche, active=True
        )

        try:
            departement = self.instance.projet.perimetre.departement
        except (AttributeError, Dossier.projet.RelatedObjectDoesNotExist):
            departement = None

        if departement:
            detr_qs = CategorieDetr.objects.filter(
                demarche=demarche, departement=departement, active=True
            ).order_by("parent_label", "rank", "label")
            self.fields["demande_categorie_detr"].queryset = detr_qs

            if detr_qs.count() != detr_qs.filter(parent_label="").count():
                # Group choices by parent_label for optgroup display
                field = self.fields["demande_categorie_detr"]
                choices = []
                if field.empty_label is not None:
                    choices.append(("", field.empty_label))
                for parent_label, categories in groupby(
                    detr_qs, key=lambda c: c.parent_label or ""
                ):
                    group_choices = [(c.pk, str(c)) for c in categories]
                    choices.append((parent_label or "—", group_choices))
                field.choices = choices
        else:
            self.fields[
                "demande_categorie_detr"
            ].queryset = CategorieDetr.objects.none()

    def save(self, commit=True):
        dotations = self.cleaned_data.get("demande_dispositif_sollicite", [])
        if DOTATION_DETR not in dotations:
            self.instance.demande_categorie_detr = None
        if DOTATION_DSIL not in dotations:
            self.instance.demande_categorie_dsil = None

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
            "demande_categorie_detr",
            "demande_categorie_dsil",
        ]
        widgets = {
            "finance_cout_total": forms.TextInput(attrs={"inputmode": "numeric"}),
            "demande_montant": forms.TextInput(attrs={"inputmode": "numeric"}),
        }
