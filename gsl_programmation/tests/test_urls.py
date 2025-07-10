import pytest
from django.urls import reverse


def test_programmation_projet_list_url():
    url = reverse("gsl_programmation:programmation-projet-list")
    assert url == "/programmation/liste/"


def test_programmation_projet_detail_url():
    url = reverse(
        "gsl_programmation:programmation-projet-detail",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/programmation/voir/123/"


@pytest.mark.parametrize(
    "tab",
    ("annotations", "historique", "notifications"),
)
def test_programmation_projet_tab_url(tab):
    """Test de l'URL des onglets"""
    url = reverse(
        "gsl_programmation:programmation-projet-tab",
        kwargs={"programmation_projet_id": 123, "tab": tab},
    )
    assert url == f"/programmation/voir/123/{tab}/"
