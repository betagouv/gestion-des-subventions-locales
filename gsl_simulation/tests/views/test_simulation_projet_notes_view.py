import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.tests.factories import DotationProjetFactory, ProjetNoteFactory
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def client_with_user_logged(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def simulation_projet(perimetre):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__perimetre=perimetre,
        dotation=DOTATION_DETR,
    )
    simulation = SimulationFactory(enveloppe=DetrEnveloppeFactory(perimetre=perimetre))
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
    )


@pytest.mark.django_db
def test_projet_note_form_save(client_with_user_logged, simulation_projet):
    projet = simulation_projet.projet
    assert projet.notes.count() == 0

    url = reverse(
        "simulation:simulation-projet-notes",
        kwargs={"pk": simulation_projet.pk},
    )
    response = client_with_user_logged.post(
        url,
        data={
            "title": "titre",
            "content": "contenu",
        },
        follow=True,
    )

    assert response.status_code == 200

    projet.refresh_from_db()
    assert projet.notes.count() == 1
    assert projet.notes.first().title == "titre"
    assert projet.notes.first().content == "contenu"


@pytest.mark.django_db
def test_projet_note_form_save_with_error(client_with_user_logged, simulation_projet):
    projet = simulation_projet.projet
    assert projet.notes.count() == 0

    url = reverse(
        "simulation:simulation-projet-notes",
        kwargs={"pk": simulation_projet.pk},
    )
    response = client_with_user_logged.post(
        url,
        data={
            "title": "12caracteres" * 13,
            "content": "",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.context["projet_note_form"].errors == {
        "title": [
            "Assurez-vous que cette valeur comporte au plus 100 caractères (actuellement 156)."
        ],
        "content": ["Ce champ est obligatoire."],
    }

    projet.refresh_from_db()
    assert projet.notes.count() == 0


@pytest.mark.parametrize(
    "is_the_logged_user_the_creator, expected_status_code, expected_note_count",
    (
        (True, 200, 0),
        (False, 404, 1),
    ),
)
@pytest.mark.django_db
def test_projet_note_deletion(
    client_with_user_logged,
    simulation_projet,
    is_the_logged_user_the_creator,
    expected_status_code,
    expected_note_count,
):
    projet = simulation_projet.projet
    if is_the_logged_user_the_creator:
        projet_note = ProjetNoteFactory(
            projet=projet,
            created_by=client_with_user_logged.user,
        )
    else:
        projet_note = ProjetNoteFactory(
            projet=projet,
        )
    assert projet.notes.count() == 1

    url = reverse(
        "simulation:simulation-projet-notes",
        kwargs={"pk": simulation_projet.pk},
    )
    response = client_with_user_logged.post(
        url,
        data={
            "action": "delete_note",
            "note_id": projet_note.id,
        },
        follow=True,
    )

    assert response.status_code == expected_status_code
    projet.refresh_from_db()
    assert projet.notes.count() == expected_note_count


@pytest.mark.django_db
def test_get_edit_projet_note(client_with_user_logged, simulation_projet):
    projet = simulation_projet.projet
    projet_note = ProjetNoteFactory(
        projet=projet, created_by=client_with_user_logged.user
    )
    assert projet.notes.count() == 1

    url = reverse(
        "simulation:get-edit-projet-note",
        kwargs={"pk": simulation_projet.pk, "note_id": projet_note.pk},
    )
    response = client_with_user_logged.get(url, headers={"HX-Request": "true"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_post_edit_projet_note(client_with_user_logged, simulation_projet):
    projet = simulation_projet.projet
    projet_note = ProjetNoteFactory(
        projet=projet, created_by=client_with_user_logged.user
    )
    assert projet.notes.count() == 1

    url = reverse(
        "simulation:get-edit-projet-note",
        kwargs={"pk": simulation_projet.pk, "note_id": projet_note.pk},
    )
    response = client_with_user_logged.post(
        url,
        headers={"HX-Request": "true"},
        data={"title": "Mon titre", "content": "Mon contenu"},
        follow=True,
    )
    assert response.status_code == 200

    projet_note.refresh_from_db()
    assert projet_note.title == "Mon titre"
    assert projet_note.content == "Mon contenu"
