from django.urls import reverse

from gsl.core.campagne import default_campagne


def test_programmation_projet_list_url():
    url = reverse(
        "gsl_programmation:programmation-projet-list",
        kwargs={"campagne": default_campagne()},
    )
    assert url == f"/programmation/liste/{default_campagne()}/"


def test_programmation_projet_list_dotation_url():
    url = reverse(
        "gsl_programmation:programmation-projet-list-dotation",
        kwargs={"dotation": "DETR", "campagne": default_campagne()},
    )
    assert url == f"/programmation/liste/DETR/{default_campagne()}/"
