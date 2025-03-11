from django import forms
from django.utils.safestring import mark_safe

from gsl_projet.models import Projet
from gsl_simulation.models import SimulationProjet


class CustomCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def _get_color(self, option_value):
        return {
            SimulationProjet.STATUS_PROCESSING: "",
            SimulationProjet.STATUS_PROVISOIRE: "blue",
            SimulationProjet.STATUS_REFUSED: "red",
            SimulationProjet.STATUS_ACCEPTED: "green",
            Projet.STATUS_ACCEPTED: "green",
            Projet.STATUS_PROCESSING: "",
            Projet.STATUS_REFUSED: "red",
            Projet.STATUS_DISMISSED: "",
        }.get(option_value, "")

    def render(self, name, value, attrs=None, renderer=None):
        """Customize how the checkboxes are displayed in the HTML output."""
        output = []
        for i, (option_value, option_label) in enumerate(self.choices):
            color = self._get_color(option_value)
            color_class = f"color-{color}" if color else ""
            checked = "checked" if value and option_value in value else ""
            checkbox = f'<input type="checkbox" name="{name}" value="{option_value}" id="id_{name}_{i}" {checked}>'
            label = f'<label for="id_{name}_{i}" class="fr-label {color_class}">{option_label}</label>'
            output.append(
                f'<div class="fr-checkbox-group fr-checkbox-group--sm">{checkbox} {label}</div>'
            )
        return mark_safe("\n".join(output))
