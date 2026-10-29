import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from dn.sync.exceptions import DsServiceException
from dn.sync.models import Dossier, Dotation
from dn.sync.tests.factories import DossierDataFactory, DossierFactory
from gsl.core.campagne import CAMPAGNES, default_campagne
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl.historique.models import ProjetAction
from gsl.notification.tests.factories import LettreRefusSigneeFactory
from gsl.programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory

from ...constants import NotificationStatus, ProjetStatus
from ...models import EnveloppeProjet, Projet
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

DS_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "dn"
    / "sync"
    / "tests"
    / "ds_fixtures"
)

CAMPAGNE = default_campagne()


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre):
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def client(collegue):
    return ClientWithLoggedUserFactory(collegue)


def _notified_projet(perimetre, *statuses, annee=CAMPAGNE, **dossier_kwargs):
    notified_at = timezone.now()
    projet = ProjetFactory(
        dossier_ds=DossierFactory(perimetre=perimetre, **dossier_kwargs),
        notified_at=notified_at,
    )
    enveloppe_factories = (DetrEnveloppeFactory, DsilEnveloppeFactory)
    for status, enveloppe_factory in zip(statuses, enveloppe_factories):
        EnveloppeProjetFactory(
            projet=projet,
            status=status,
            enveloppe=enveloppe_factory(perimetre=perimetre, annee=annee),
            notified_at=notified_at,
        )
    return projet


def _url(projet):
    return reverse("gsl_projet:reporter", kwargs={"projet_id": projet.id})


def _post(client, projet):
    return client.post(_url(projet), {}, headers={"HX-Request": "true"})


# can_be_reported =======================================================================


@pytest.mark.parametrize(
    "statuses, expected",
    (
        ((ProjetStatus.REFUSED,), True),
        ((ProjetStatus.DISMISSED,), True),
        ((ProjetStatus.ACCEPTED, ProjetStatus.REFUSED), True),
        ((ProjetStatus.REFUSED, ProjetStatus.DISMISSED), True),
        ((ProjetStatus.ACCEPTED,), False),
        ((ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED), False),
    ),
)
def test_can_be_reporte_depends_on_the_statuses(perimetre, statuses, expected):
    assert _can_be_reported(_notified_projet(perimetre, *statuses)) is expected


def test_a_projet_with_a_non_notified_actif_cannot_be_reported(perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED, ProjetStatus.REFUSED)
    dsil = projet.dotation_dsil
    dsil.notified_at = None
    dsil.save()

    assert _can_be_reported(projet) is False


def test_a_projet_cannot_be_reporte_beyond_the_last_campagne(perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED, annee=CAMPAGNE + 1)

    assert _can_be_reported(projet) is False


def test_reporter_refuses_a_projet_on_the_last_campagne(perimetre):
    from django.core.exceptions import ValidationError

    derniere = max(CAMPAGNES)
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED, annee=derniere)

    with pytest.raises(ValidationError, match=f"La campagne {derniere + 1} n'existe"):
        projet.reporter()
    assert not EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=derniere + 1
    ).exists()


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_a_reporte_projet_cannot_be_reporte_again(_mock, client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)
    _post(client, projet)
    projet.refresh_from_db()

    assert _can_be_reported(projet) is False


def _can_be_reported(projet):
    """The queryset and its Python side twin must agree."""
    projet = Projet.objects.get(pk=projet.pk)
    in_queryset = Projet.objects.can_be_reported().filter(pk=projet.pk).exists()
    assert projet.can_be_reported is in_queryset
    return in_queryset


# Modal ================================================================================


def test_get_modal_returns_confirmation(client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)

    response = client.get(_url(projet), headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert f"Reporter le projet sur la campagne {CAMPAGNE + 1}" in (
        response.content.decode()
    )


def test_get_modal_returns_404_when_the_projet_cannot_be_reporte(client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.ACCEPTED)

    response = client.get(_url(projet), headers={"HX-Request": "true"})

    assert response.status_code == 404


def test_the_button_is_displayed_only_when_the_projet_can_be_reported(
    client, perimetre
):
    reportable = _notified_projet(perimetre, ProjetStatus.REFUSED)
    non_reportable = _notified_projet(perimetre, ProjetStatus.ACCEPTED)

    def page(projet):
        return client.get(
            reverse("gsl_projet:get-projet", kwargs={"projet_id": projet.id})
        ).content.decode()

    assert "Reporter le projet" in page(reportable)
    assert "Reporter le projet" not in page(non_reportable)


# Report ===============================================================================


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_simple_dotation_report(mock_repasser, client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)
    (ancien,) = EnveloppeProjet.objects.filter(projet=projet)

    _post(client, projet)

    mock_repasser.assert_called_once()
    ancien.refresh_from_db()
    assert ancien.is_courant is True
    assert ancien.status == ProjetStatus.REFUSED
    assert ancien.notification_status == NotificationStatus.NOTIFIED
    (nouveau,) = EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    )
    assert nouveau.dotation == Dotation.DETR
    assert nouveau.status == ProjetStatus.PROCESSING
    assert nouveau.notified_at is None
    (action,) = ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_REPORT
    )
    assert action.action_label == f"Report DETR de la campagne {CAMPAGNE} sur " + str(
        CAMPAGNE + 1
    )


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_only_the_refused_dotation_is_reporte(_mock, client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.ACCEPTED, ProjetStatus.REFUSED)

    _post(client, projet)

    nouveaux = EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    )
    assert [ep.dotation for ep in nouveaux] == [Dotation.DSIL]


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_both_refused_or_dismissed_dotations_are_reportees(_mock, client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED, ProjetStatus.DISMISSED)

    _post(client, projet)

    nouveaux = EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    )
    assert sorted(ep.dotation for ep in nouveaux) == [Dotation.DETR, Dotation.DSIL]


@patch(
    "gsl.projet.forms.DsService.repasser_en_instruction",
    side_effect=DsServiceException("DN indisponible"),
)
def test_a_dn_failure_rolls_the_report_back(_mock, client, perimetre):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)

    _post(client, projet)

    assert not EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    ).exists()
    assert not ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_REPORT
    ).exists()


# With the real DN sync (only the network call is faked) ===============================


def _ds_repasser_en_instruction_response(date: str) -> dict:
    return {
        "data": {
            "dossierRepasserEnInstruction": {
                "dossier": {
                    "dateDerniereModification": date,
                    "state": "en_instruction",
                    "traitements": [
                        {
                            "id": "traitement-1",
                            "dateTraitement": date,
                            "event": "repasse_en_instruction",
                        }
                    ],
                }
            }
        }
    }


def test_the_dn_sync_after_a_report_keeps_the_campagne_reportee_untouched(
    client, perimetre
):
    projet = _notified_projet(
        perimetre,
        ProjetStatus.ACCEPTED,
        ProjetStatus.REFUSED,
        porteur_de_projet_arrondissement=None,
        porteur_de_projet_departement=perimetre.departement,
        ds_state=Dossier.State.ACCEPTE,
    )
    with open(DS_FIXTURES_DIR / "dossier_data.json") as handle:
        DossierDataFactory(dossier=projet.dossier_ds, raw_data=json.load(handle))
    anciens = {
        ep.pk: (ep.status, ep.notified_at)
        for ep in EnveloppeProjet.objects.filter(projet=projet)
    }

    with patch(
        "dn.sync.ds_client.DsMutator.dossier_repasser_en_instruction",
        return_value=_ds_repasser_en_instruction_response(timezone.now().isoformat()),
    ):
        _post(client, projet)

    projet.refresh_from_db()
    assert projet.notified_at is None
    for pk, (status, notified_at) in anciens.items():
        ancien = EnveloppeProjet.objects.get(pk=pk)
        assert (ancien.status, ancien.notified_at) == (status, notified_at)
    (nouveau,) = EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    )
    assert (nouveau.dotation, nouveau.status) == (
        Dotation.DSIL,
        ProjetStatus.PROCESSING,
    )


# After the report =====================================================================


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_an_enveloppe_projet_reporte_cannot_be_set_back_to_processing(
    _mock, client, perimetre
):
    from django_fsm import TransitionNotAllowed

    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)
    (ancien,) = EnveloppeProjet.objects.filter(projet=projet)
    _post(client, projet)

    with pytest.raises(TransitionNotAllowed):
        ancien.set_back_status_to_processing_without_ds()


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_the_projet_only_exposes_the_dotations_of_the_campagne_reportee(
    _mock, client, perimetre
):
    projet = _notified_projet(perimetre, ProjetStatus.ACCEPTED, ProjetStatus.REFUSED)
    _post(client, projet)
    projet.refresh_from_db()

    assert projet.dotations == [Dotation.DSIL]
    assert projet.dotation_detr is None
    assert projet.dotation_dsil.enveloppe.annee == CAMPAGNE + 1
    assert projet.has_double_dotations is False


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_the_documents_of_the_campagne_reportee_are_not_sent_again(
    _mock, client, perimetre
):
    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)
    (ancien,) = EnveloppeProjet.objects.filter(projet=projet)
    LettreRefusSigneeFactory(enveloppe_projet=ancien)
    assert len(projet.imported_documents) == 1

    _post(client, projet)

    assert projet.imported_documents == []


def test_a_retour_en_instruction_after_the_report_only_reopens_the_campagne_suivante(
    perimetre,
):
    from datetime import UTC, datetime

    from ...services.enveloppe_projet_services import EnveloppeProjetService

    notification_n = datetime(CAMPAGNE, 3, 1, tzinfo=UTC)
    notification_n_plus_1 = datetime(CAMPAGNE + 1, 3, 1, tzinfo=UTC)
    projet = ProjetFactory(
        dossier_ds=DossierFactory(
            perimetre=perimetre,
            demande_dispositif_sollicite="DETR",
            ds_state=Dossier.State.EN_INSTRUCTION,
            ds_date_traitement=notification_n_plus_1,
            ds_date_passage_en_instruction=datetime(CAMPAGNE + 1, 4, 1, tzinfo=UTC),
        )
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE),
        date_programmation=notification_n,
        notified_at=notification_n,
    )
    reporte = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE + 1),
        date_programmation=notification_n_plus_1,
        notified_at=notification_n_plus_1,
    )

    EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet(projet)

    closed.refresh_from_db()
    reporte.refresh_from_db()
    assert (closed.is_courant, closed.status, closed.notified_at) == (
        True,
        ProjetStatus.REFUSED,
        notification_n,
    )
    assert reporte.is_courant is False
    (courant,) = EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    )
    assert courant.status == ProjetStatus.PROCESSING


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_the_simulation_of_the_campagne_suivante_shows_the_enveloppe_projet_reporte(
    _mock, client, perimetre
):
    from gsl.simulation.tests.factories import SimulationFactory

    projet = _notified_projet(perimetre, ProjetStatus.REFUSED)
    simulation = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE + 1)
    )
    _post(client, projet)

    response = client.get(
        reverse("gsl_simulation:simulation-detail", kwargs={"slug": simulation.slug})
    )

    assert response.status_code == 200
    (row,) = response.context["page_obj"].object_list
    (enveloppe_projet,) = row.enveloppe_projet
    assert enveloppe_projet.enveloppe.annee == CAMPAGNE + 1
    assert len(enveloppe_projet.simu) == 1


@pytest.mark.parametrize(
    "statuses, has_accepted",
    (
        ((ProjetStatus.REFUSED,), False),
        ((ProjetStatus.ACCEPTED, ProjetStatus.REFUSED), True),
    ),
)
@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_the_dotations_of_the_campagne_reportee_still_count_as_treated(
    _mock, client, perimetre, statuses, has_accepted
):
    projet = _notified_projet(perimetre, *statuses)
    _post(client, projet)
    projet.refresh_from_db()
    assert all(
        ep.status == ProjetStatus.PROCESSING for ep in projet.enveloppe_projets_actifs
    )

    assert projet.has_treated_dotation is True
    assert projet.can_display_notification_tab is True
    assert projet.has_accepted_dotation is has_accepted
    assert projet.can_display_suivi_financier_tab is has_accepted
