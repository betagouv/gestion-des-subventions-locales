from django import template

from gsl_projet.forms import DotationProjetAssietteForm

register = template.Library()


@register.inclusion_tag("includes/forms/_assiette_dotation_projet_form.html")
def assiette_dotation_form(dotation_projet):
    return {
        "dotation_projet": dotation_projet,
        "form": DotationProjetAssietteForm(instance=dotation_projet),
    }
