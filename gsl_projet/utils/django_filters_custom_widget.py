from django import forms
from django.utils.safestring import mark_safe


class CustomCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def render(self, name, value, attrs=None, renderer=None):
        """Customize how the checkboxes are displayed in the HTML output."""
        output = []
        for i, (option_value, option_label) in enumerate(self.choices):
            checked = "checked" if option_value in value else ""
            checkbox = f'<input type="checkbox" name="{name}" value="{option_value}" id="id_{name}_{i}" {checked}>'
            label = (
                f'<label for="id_{name}_{i}" class="fr-label">{option_label}</label>'
            )
            output.append(
                f'<div class="fr-checkbox-group fr-checkbox-group--sm">{checkbox} {label}</div>'
            )
        return mark_safe("\n".join(output))
