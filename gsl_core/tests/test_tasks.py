import pytest

from gsl_core.tasks import associate_or_update_ds_id_to_user
from gsl_core.tests.factories import CollegueFactory
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory


@pytest.mark.django_db
def test_associate_or_update_ds_id_to_user():
    user_without_id = CollegueFactory(email="user1@example.com")
    user_with_id = CollegueFactory(email="user2@example.com", ds_id="azertyui")
    user_not_in_demarche = CollegueFactory(email="user3@example.com")

    DemarcheFactory(
        raw_ds_data={
            "groupeInstructeurs": [
                {
                    "instructeurs": [
                        {"email": "user1@example.com", "id": "123456789"},
                        {"email": "user2@example.com", "id": "abcdefgh"},
                    ]
                }
            ]
        }
    )

    associate_or_update_ds_id_to_user()

    user_without_id.refresh_from_db()
    assert user_without_id.ds_id == "123456789"

    user_with_id.refresh_from_db()
    assert user_with_id.ds_id == "abcdefgh"

    user_not_in_demarche.refresh_from_db()
    assert user_not_in_demarche.ds_id == ""
