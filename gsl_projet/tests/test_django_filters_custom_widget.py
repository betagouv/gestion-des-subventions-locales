"""Unit tests for the `active_tag_label` self-description added to the custom
filter widgets. Each widget formats its own dismissible active-filter tag."""

from datetime import date

from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    DsfrDateRangeWidget,
    DsfrRangeWidget,
)


class TestDsfrRangeWidgetActiveTagLabel:
    def test_both_bounds(self):
        widget = DsfrRangeWidget()
        label = widget.active_tag_label(slice(1000, 5000), "Montant demandé")
        assert label == "Montant demandé de 1 000 € à 5 000 €"

    def test_only_lower_bound(self):
        widget = DsfrRangeWidget()
        assert widget.active_tag_label(slice(1000, None), "Coût total") == (
            "Coût total supérieur à 1 000 €"
        )

    def test_only_upper_bound(self):
        widget = DsfrRangeWidget()
        assert widget.active_tag_label(slice(None, 5000), "Coût total") == (
            "Coût total inférieur à 5 000 €"
        )

    def test_empty(self):
        widget = DsfrRangeWidget()
        assert widget.active_tag_label(None, "Coût total") == ""
        assert widget.active_tag_label(slice(None, None), "Coût total") == ""


class TestDsfrDateRangeWidgetActiveTagLabel:
    def test_both_bounds(self):
        widget = DsfrDateRangeWidget()
        label = widget.active_tag_label(
            slice(date(2024, 1, 2), date(2024, 3, 4)), "Date de dépôt"
        )
        assert label == "Date de dépôt du 02/01/2024 au 04/03/2024"

    def test_only_lower_bound(self):
        widget = DsfrDateRangeWidget()
        assert (
            widget.active_tag_label(slice(date(2024, 1, 2), None), "Date de dépôt")
            == "Date de dépôt à partir du 02/01/2024"
        )

    def test_only_upper_bound(self):
        widget = DsfrDateRangeWidget()
        assert (
            widget.active_tag_label(slice(None, date(2024, 3, 4)), "Date de dépôt")
            == "Date de dépôt jusqu'au 04/03/2024"
        )

    def test_empty(self):
        widget = DsfrDateRangeWidget()
        assert widget.active_tag_label(None, "Date de dépôt") == ""
        assert widget.active_tag_label(slice(None, None), "Date de dépôt") == ""


class TestCustomCheckboxSelectMultipleActiveTagLabel:
    def test_single_choice(self):
        widget = CustomCheckboxSelectMultiple()
        widget.choices = [("epci", "EPCI"), ("communes", "Communes")]
        assert widget.active_tag_label(["epci"], "Demandeur") == "Demandeur : EPCI"

    def test_several_choices_are_joined(self):
        widget = CustomCheckboxSelectMultiple()
        widget.choices = [("epci", "EPCI"), ("communes", "Communes")]
        assert widget.active_tag_label(["epci", "communes"], "Demandeur") == (
            "Demandeur : EPCI, Communes"
        )

    def test_model_instances_resolve_by_pk(self):
        """Model/LabelFromInstance filters pass a queryset of instances; the
        widget resolves each against its own pk-keyed choice labels."""

        class FakeInstance:
            def __init__(self, pk):
                self.pk = pk

        widget = CustomCheckboxSelectMultiple()
        widget.choices = [(1, "Catégorie A"), (2, "Catégorie B")]
        value = [FakeInstance(2)]
        assert widget.active_tag_label(value, "Catégorie") == "Catégorie : Catégorie B"

    def test_model_instances_use_label_attr_when_set(self):
        """When `label_attr` is configured, model instances are labelled via that
        attribute (mirroring the filter's `label_from_instance`), independently
        of `self.choices` / `str()`."""

        class FakeInstance:
            def __init__(self, pk, entity_name):
                self.pk = pk
                self.entity_name = entity_name

            def __str__(self):
                return f"Département | Île-de-France - {self.entity_name}"

        widget = CustomCheckboxSelectMultiple(label_attr="entity_name")
        widget.choices = []  # nothing to resolve against
        value = [FakeInstance(2, "Paris")]
        assert widget.active_tag_label(value, "Territoire") == "Territoire : Paris"

    def test_empty(self):
        widget = CustomCheckboxSelectMultiple()
        widget.choices = [("epci", "EPCI")]
        assert widget.active_tag_label([], "Demandeur") == ""
        assert widget.active_tag_label(None, "Demandeur") == ""
