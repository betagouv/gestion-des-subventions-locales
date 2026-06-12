from django import forms
from django.utils.safestring import mark_safe
from django_filters.widgets import SuffixedMultiWidget

from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_simulation.models import SimulationProjet


class CustomCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def __init__(self, *args, placeholder=None, display_template=None, **kwargs):
        self.placeholder = placeholder
        self.display_template = display_template or "includes/_filter_multiselect.html"
        super().__init__(*args, **kwargs)

    def _get_color(self, option_value):
        return {
            SimulationProjet.STATUS_PROCESSING: "",
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: "blue",
            SimulationProjet.STATUS_PROVISIONALLY_REFUSED: "brown",
            SimulationProjet.STATUS_REFUSED: "red",
            SimulationProjet.STATUS_ACCEPTED: "green",
            PROJET_STATUS_ACCEPTED: "green",
            PROJET_STATUS_PROCESSING: "",
            PROJET_STATUS_REFUSED: "red",
            PROJET_STATUS_DISMISSED: "",
            ProgrammationProjet.STATUS_ACCEPTED: "green",
            ProgrammationProjet.STATUS_REFUSED: "red",
        }.get(option_value, "")

    def render(self, name, value, attrs=None, renderer=None):
        """Customize how the checkboxes are displayed in the HTML output."""
        output = []
        str_values = {str(v) for v in value} if value else set()
        for i, (option_value, option_label) in enumerate(self.choices):
            color = self._get_color(option_value)
            color_class = f"color-{color}" if color else ""
            checked = "checked" if str(option_value) in str_values else ""
            checkbox = f'<input type="checkbox" name="{name}" value="{option_value}" id="id_{name}_{i}" {checked}>'
            label = f'<label for="id_{name}_{i}" class="fr-label {color_class}">{option_label}</label>'
            output.append(
                f'<div class="fr-checkbox-group fr-checkbox-group--sm">{checkbox} {label}</div>'
            )
        return mark_safe("\n".join(output))

    def active_tag_label(self, value, label):
        """Tag text joining the labels of the selected choices, or '' if none.

        `value` is a list of submitted values (MultipleChoiceFilter) or a
        queryset of model instances (Model/LabelFromInstance filters); both
        resolve against the widget's own `str()`-keyed choice labels."""
        if not value:
            return ""
        choice_dict = {str(k): v for k, v in self.choices}
        parts = []
        for item in value:
            key = str(item.pk) if hasattr(item, "pk") else str(item)
            parts.append(str(choice_dict.get(key, item)))
        return f"{label} : {', '.join(parts)}"


class DsfrRangeWidget(SuffixedMultiWidget):
    suffixes = ["min", "max"]

    def __init__(self, attrs=None, icon=None, display_template=None):
        self.icon = icon
        self.display_template = display_template or "includes/_filter_amount_range.html"
        default_attrs = {"class": "fr-input", "min": "0"}
        if attrs:
            default_attrs.update(attrs)
        widgets = (
            forms.NumberInput(attrs=dict(default_attrs)),
            forms.NumberInput(attrs=dict(default_attrs)),
        )
        super().__init__(widgets, None)

    def decompress(self, value):
        if value:
            return [value.start, value.stop]
        return [None, None]

    def active_tag_label(self, value, label):
        """Euro span ("de … à …" / "supérieur à …" / "inférieur à …"), or ''."""
        from gsl_core.templatetags.gsl_filters import euro

        if value is None:
            return ""
        start, stop = value.start, value.stop
        if start is None and stop is None:
            return ""
        if start is not None and stop is not None:
            return f"{label} de {euro(start)} à {euro(stop)}"
        if start is not None:
            return f"{label} supérieur à {euro(start)}"
        return f"{label} inférieur à {euro(stop)}"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for subcontext, suffix in zip(context["widget"]["subwidgets"], self.suffixes):
            subcontext["attrs"]["id"] = f"id_{self.suffixed(name, suffix)}"
        return context

    def get_decomposed_context(self, bound_field):
        name = bound_field.name
        value = bound_field.value()
        if not isinstance(value, list):
            value = self.decompress(value)
        min_name = self.suffixed(name, "min")
        max_name = self.suffixed(name, "max")
        form_data = bound_field.form.data
        return {
            "min_widget": self.widgets[0].render(
                min_name,
                value[0],
                {"class": "fr-input", "min": "0", "id": f"id_{min_name}"},
            ),
            "max_widget": self.widgets[1].render(
                max_name,
                value[1],
                {"class": "fr-input", "min": "0", "id": f"id_{max_name}"},
            ),
            "min_name": min_name,
            "max_name": max_name,
            "has_data": bool(form_data.get(min_name) or form_data.get(max_name)),
            "min_value": form_data.get(min_name, ""),
            "max_value": form_data.get(max_name, ""),
            "label": bound_field.label,
            "icon": self.icon,
        }


class DsfrDateRangeWidget(SuffixedMultiWidget):
    suffixes = ["after", "before"]

    def __init__(self, attrs=None, icon=None, display_template=None):
        self.icon = icon
        self.display_template = display_template or "includes/_filter_date_range.html"
        default_attrs = {"class": "fr-input", "type": "date"}
        if attrs:
            default_attrs.update(attrs)
        widgets = (
            forms.DateInput(attrs=dict(default_attrs)),
            forms.DateInput(attrs=dict(default_attrs)),
        )
        super().__init__(widgets, None)

    def decompress(self, value):
        if value:
            return [value.start, value.stop]
        return [None, None]

    def active_tag_label(self, value, label):
        """Date span ("du … au …" / "à partir du …" / "jusqu'au …"), or ''."""
        if value is None:
            return ""
        d1 = value.start.strftime("%d/%m/%Y") if value.start else None
        d2 = value.stop.strftime("%d/%m/%Y") if value.stop else None
        if not d1 and not d2:
            return ""
        if d1 and d2:
            return f"{label} du {d1} au {d2}"
        if d1:
            return f"{label} à partir du {d1}"
        return f"{label} jusqu'au {d2}"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for subcontext, suffix in zip(context["widget"]["subwidgets"], self.suffixes):
            subcontext["attrs"]["id"] = f"id_{self.suffixed(name, suffix)}"
        return context

    def get_decomposed_context(self, bound_field):
        name = bound_field.name
        value = bound_field.value()
        if not isinstance(value, list):
            value = self.decompress(value)
        min_value, max_value = value
        min_name = self.suffixed(name, "after")
        max_name = self.suffixed(name, "before")
        form_data = bound_field.form.data
        return {
            "min_widget": self.widgets[0].render(
                min_name,
                min_value,
                {"class": "fr-input", "type": "date", "id": f"id_{min_name}"},
            ),
            "max_widget": self.widgets[1].render(
                max_name,
                max_value,
                {"class": "fr-input", "type": "date", "id": f"id_{max_name}"},
            ),
            "min_name": min_name,
            "max_name": max_name,
            "has_data": bool(form_data.get(min_name) or form_data.get(max_name)),
            "min_value": form_data.get(min_name, ""),
            "max_value": form_data.get(max_name, ""),
            "label": bound_field.label,
            "icon": self.icon,
        }


class CustomSelectWidget(forms.Select):
    display_template = "includes/_filter_select.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"]["class"] = "fr-select"
        return context
