from django.urls import reverse


def test_programmation_projet_list_url():
    url = reverse("gsl_programmation:programmation-projet-list")
    assert url == "/programmation/liste/"


def test_programmation_projet_list_dotation_url():
    url = reverse(
        "gsl_programmation:programmation-projet-list-dotation",
        kwargs={"dotation": "DETR"},
    )
    assert url == "/programmation/liste/DETR/"


def test_programmation_projet_detail_url():
    url = reverse(
        "gsl_programmation:programmation-projet-detail",
        kwargs={"projet_id": 123},
    )
    assert url == "/programmation/voir/123/"


def test_programmation_projet_notes_url():
    url = reverse(
        "gsl_programmation:programmation-projet-notes",
        kwargs={"projet_id": 123},
    )
    assert url == "/programmation/voir/123/notes/"
