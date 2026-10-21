from unittest.mock import patch

from dn.sync.ds_client import DsMutator


def test_dossier_classer_sans_suite():
    ds_mutator = DsMutator()
    with patch("dn.sync.ds_client.DsMutator._mutate_dossier") as mock_mutate_dossier:
        ds_mutator.dossier_classer_sans_suite(
            "dossier_id", "instructeur_id", "motivation"
        )
        mock_mutate_dossier.assert_called_once_with(
            "dossierClasserSansSuite",
            "dossier_id",
            "instructeur_id",
            "motivation",
            None,  # the document
        )
