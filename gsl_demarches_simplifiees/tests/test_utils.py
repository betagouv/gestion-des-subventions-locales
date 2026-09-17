from gsl_demarches_simplifiees.utils import most_recent_traitement


def test_most_recent_traitement_ignores_list_order():
    traitements = [
        {"id": "older", "dateTraitement": "2025-01-10T00:00:00+00:00"},
        {"id": "newer", "dateTraitement": "2025-01-20T00:00:00+00:00"},
    ]

    assert most_recent_traitement(traitements)["id"] == "newer"


def test_most_recent_traitement_skips_entries_without_a_date():
    traitements = [
        {"id": "no-date"},
        {"id": "with-date", "dateTraitement": "2025-01-10T00:00:00+00:00"},
    ]

    assert most_recent_traitement(traitements)["id"] == "with-date"


def test_most_recent_traitement_returns_none_when_empty_or_no_date():
    assert most_recent_traitement([]) is None
    assert most_recent_traitement([{"id": "no-date"}]) is None
