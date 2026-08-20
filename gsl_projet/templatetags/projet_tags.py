from django import template

from gsl_projet.forms import DotationProjetAssietteForm, DotationProjetForm

register = template.Library()


@register.inclusion_tag("includes/forms/_assiette_dotation_projet_form.html")
def assiette_dotation_form(dotation_projet):
    return {
        "dotation_projet": dotation_projet,
        "form": DotationProjetAssietteForm(instance=dotation_projet),
    }


@register.inclusion_tag("includes/forms/_detr_avis_commission_form.html")
def detr_avis_commission_form(dotation_projet):
    return {
        "dotation_projet": dotation_projet,
        "form": DotationProjetForm(instance=dotation_projet),
    }
