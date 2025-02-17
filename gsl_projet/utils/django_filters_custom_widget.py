from django import forms
from django.utils.safestring import mark_safe

from gsl_demarches_simplifiees.models import Dossier
from gsl_simulation.models import SimulationProjet


class CustomCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def _get_color(self, option_value):
        return {
            SimulationProjet.STATUS_PROCESSING: "",
            SimulationProjet.STATUS_PROVISOIRE: "blue",
            SimulationProjet.STATUS_REFUSED: "red",
            SimulationProjet.STATUS_ACCEPTED: "green",
            Dossier.STATE_ACCEPTE: "green",
            Dossier.STATE_EN_CONSTRUCTION: "blue",
            Dossier.STATE_EN_INSTRUCTION: "blue",
            Dossier.STATE_REFUSE: "red",
            Dossier.STATE_SANS_SUITE: "orange",
        }.get(option_value, "")

    def render(self, name, value, attrs=None, renderer=None):
        """Customize how the checkboxes are displayed in the HTML output."""
        output = []
        for i, (option_value, option_label) in enumerate(self.choices):
            color = self._get_color(option_value)
            style = f'style="color: var(--status-color-{color});"' if color else ""
            checked = "checked" if value and option_value in value else ""
            checkbox = f'<input type="checkbox" name="{name}" value="{option_value}" id="id_{name}_{i}" {checked}>'
            label = f'<label for="id_{name}_{i}" class="fr-label" {style}>{option_label}</label>'
            output.append(
                f'<div class="fr-checkbox-group fr-checkbox-group--sm">{checkbox} {label}</div>'
            )
        return mark_safe("\n".join(output))
