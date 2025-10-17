from unittest.mock import patch

from gsl_demarches_simplifiees.ds_client import DsMutator


def test_dossier_classer_sans_suite():
    ds_mutator = DsMutator()
    with patch(
        "gsl_demarches_simplifiees.ds_client.DsMutator._mutate_with_justificatif_and_motivation"
    ) as mock_mutate_with_justificatif_and_motivation:
        ds_mutator.dossier_classer_sans_suite(
            "dossier_id", "instructeur_id", "motivation"
        )
        mock_mutate_with_justificatif_and_motivation.assert_called_once_with(
            "dossierClasserSansSuite",
            "dossier_id",
            "instructeur_id",
            "motivation",
            None,
        )
