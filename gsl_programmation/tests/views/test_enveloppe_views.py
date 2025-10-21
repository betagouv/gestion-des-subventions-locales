import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_simulation.tests.factories import SimulationFactory

pytestmark = pytest.mark.django_db


class TestSubEnveloppeSecurity:
    def test_can_only_edit_delegated_enveloppe(self):
        # Setup a user with a departmental perimeter
        user = CollegueFactory()
        perimetre_dept = PerimetreDepartementalFactory()
        user.perimetre = perimetre_dept
        user.save()
        client = ClientWithLoggedUserFactory(user=user)

        # Parent DETR envelope at departmental level (should not be editable)
        parent_enveloppe = DetrEnveloppeFactory(perimetre=perimetre_dept, annee=2024)

        # Delegated child envelope at arrondissement level within the same department
        from gsl_core.tests.factories import ArrondissementFactory

        arrondissement = ArrondissementFactory(departement=perimetre_dept.departement)
        perimetre_arr = PerimetreArrondissementFactory(arrondissement=arrondissement)
        delegated_child = Enveloppe.objects.create(
            dotation=DOTATION_DETR,
            montant=1000,
            annee=parent_enveloppe.annee,
            perimetre=perimetre_arr,
            deleguee_by=parent_enveloppe,
        )

        # Delegated envelope outside user's perimeter (should NOT be editable)
        other_dept = PerimetreDepartementalFactory()
        other_parent = DetrEnveloppeFactory(perimetre=other_dept, annee=2024)
        other_arrondissement = ArrondissementFactory(departement=other_dept.departement)
        other_arr = PerimetreArrondissementFactory(arrondissement=other_arrondissement)
        delegated_outside = Enveloppe.objects.create(
            dotation=DOTATION_DETR,
            montant=2000,
            annee=other_parent.annee,
            perimetre=other_arr,
            deleguee_by=other_parent,
        )

        # Allowed: can edit delegated sub-enveloppe within their perimeter/children
        url_allowed = reverse("gsl_projet:enveloppe-update", args=[delegated_child.id])
        response = client.get(url_allowed)
        assert response.status_code == 200

        # Not allowed: non-delegated envelope should 404
        url_not_delegated = reverse(
            "gsl_projet:enveloppe-update", args=[parent_enveloppe.id]
        )
        response = client.get(url_not_delegated)
        assert response.status_code == 404

        # Not allowed: delegated envelope outside perimeter should 404
        url_outside = reverse(
            "gsl_projet:enveloppe-update", args=[delegated_outside.id]
        )
        response = client.get(url_outside)
        assert response.status_code == 404

    def test_cannot_create_higher_perimeter_enveloppe(self):
        # Setup a user with a departmental perimeter
        user = CollegueFactory()
        perimetre_dept = PerimetreDepartementalFactory()
        user.perimetre = perimetre_dept
        user.save()
        client = ClientWithLoggedUserFactory(user=user)

        # There is a regional perimeter in the same region
        perimetre_region = PerimetreRegionalFactory(region=perimetre_dept.region)

        # Access the create form and ensure the regional perimeter is not selectable
        url = reverse("gsl_projet:enveloppe-create")
        response = client.get(url)
        assert response.status_code == 200
        form = response.context["form"]
        perimetre_queryset = form.fields["perimetre"].queryset
        assert perimetre_region not in perimetre_queryset

    def test_cannot_create_other_department_enveloppe(self):
        # Setup a user with a departmental perimeter
        user = CollegueFactory()
        perimetre_dept = PerimetreDepartementalFactory()
        user.perimetre = perimetre_dept
        user.save()
        client = ClientWithLoggedUserFactory(user=user)

        # Create an arrondissement perimeter in another department (same region)
        from gsl_core.tests.factories import ArrondissementFactory, DepartementFactory

        other_dept = DepartementFactory(region=perimetre_dept.region)
        other_arrondissement = ArrondissementFactory(departement=other_dept)
        perimetre_other_arr = PerimetreArrondissementFactory(
            arrondissement=other_arrondissement
        )

        # Access the create form and ensure the other-department perimeter is not selectable
        url = reverse("gsl_projet:enveloppe-create")
        response = client.get(url)
        assert response.status_code == 200
        form = response.context["form"]
        perimetre_queryset = form.fields["perimetre"].queryset
        assert perimetre_other_arr not in perimetre_queryset


class TestSubEnveloppeDeleteView:
    def test_delete_enveloppe_with_simulations_shows_error(self):
        # Setup a user with a departmental perimeter
        user = CollegueFactory()
        perimetre_arr = PerimetreArrondissementFactory()
        perimetre_dept = PerimetreDepartementalFactory(
            departement=perimetre_arr.departement, region=perimetre_arr.region
        )
        user.perimetre = perimetre_dept
        user.save()
        client = ClientWithLoggedUserFactory(user=user)

        # Create a delegated sub-enveloppe
        parent_enveloppe = DsilEnveloppeFactory(perimetre=perimetre_dept, annee=2024)
        sub_enveloppe = Enveloppe.objects.create(
            dotation=DOTATION_DSIL,
            montant=1500,
            annee=parent_enveloppe.annee,
            perimetre=perimetre_arr,
            deleguee_by=parent_enveloppe,
        )

        # Create a simulation linked to the sub-enveloppe
        SimulationFactory(enveloppe=sub_enveloppe)

        # Attempt to delete the sub-enveloppe
        url = reverse("gsl_projet:enveloppe-delete", args=[sub_enveloppe.id])
        response = client.post(url, follow=True)

        # Check that an error message is shown
        assert response.status_code == 200
        message = list(response.context["messages"])[0]
        assert (
            "Suppression impossible : 1 simulation est rattachée à cette enveloppe."
            == message.message
        )
