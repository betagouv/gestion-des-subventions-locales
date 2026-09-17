import logging

from gsl_demarches_simplifiees.utils import most_recent_traitement


def test_most_recent_traitement_ignores_list_order():
    traitements = [
        {"id": "older", "dateTraitement": "2025-01-10T00:00:00+00:00", "event": "x"},
        {"id": "newer", "dateTraitement": "2025-01-20T00:00:00+00:00", "event": "x"},
    ]

    assert most_recent_traitement(traitements, "x")["id"] == "newer"


def test_most_recent_traitement_skips_entries_without_a_date():
    traitements = [
        {"id": "no-date", "event": "x"},
        {
            "id": "with-date",
            "dateTraitement": "2025-01-10T00:00:00+00:00",
            "event": "x",
        },
    ]

    assert most_recent_traitement(traitements, "x")["id"] == "with-date"


def test_most_recent_traitement_returns_none_when_empty_or_no_date():
    assert most_recent_traitement([], "x") is None
    assert most_recent_traitement([{"id": "no-date"}], "x") is None


def test_most_recent_traitement_returns_none_when_event_does_not_match(caplog):
    """A mismatch between the most recent traitement's event and the
    expected one is logged as an anomaly, and no traitement is returned:
    guessing the wrong one would be worse than returning nothing."""
    traitements = [
        {
            "id": "newer",
            "dateTraitement": "2025-01-20T00:00:00+00:00",
            "event": "refuse",
        }
    ]

    with caplog.at_level(logging.ERROR):
        result = most_recent_traitement(traitements, "accepte")

    assert result is None
    assert "ne correspond pas à l'événement attendu" in caplog.text


def test_most_recent_traitement_does_not_log_when_event_matches(caplog):
    traitements = [
        {
            "id": "newer",
            "dateTraitement": "2025-01-20T00:00:00+00:00",
            "event": "accepte",
        }
    ]

    with caplog.at_level(logging.ERROR):
        result = most_recent_traitement(traitements, "accepte")

    assert result["id"] == "newer"
    assert caplog.text == ""


def test_most_recent_traitement_does_not_log_when_nothing_found(caplog):
    with caplog.at_level(logging.ERROR):
        result = most_recent_traitement([], "accepte")

    assert result is None
    assert caplog.text == ""
