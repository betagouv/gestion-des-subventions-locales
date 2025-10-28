import kombu
import pytest

from gsl_core.models import Collegue
from gsl_core.tasks import associate_or_update_ds_profile_to_users
from gsl_core.tests.factories import CollegueFactory
from gsl_demarches_simplifiees.tests.factories import ProfileFactory


@pytest.mark.django_db
def test_associate_or_update_ds_profile_to_users():
    user_without_ds_profile = CollegueFactory(
        email="user1@example.com", ds_profile=None
    )
    user_with_ds_profile = CollegueFactory(
        email="user2@example.com", ds_profile=ProfileFactory()
    )
    user_not_in_ds_profiles = CollegueFactory(email="user3@example.com")

    ProfileFactory(ds_email="user1@example.com", ds_id="123456789")
    ProfileFactory(ds_email="user2@example.com", ds_id="abcdefgh")

    user_ids = list(Collegue.objects.values_list("id", flat=True))
    associate_or_update_ds_profile_to_users(user_ids)

    user_without_ds_profile.refresh_from_db()
    assert user_without_ds_profile.ds_id == "123456789"

    user_with_ds_profile.refresh_from_db()
    assert user_with_ds_profile.ds_id == "abcdefgh"

    user_not_in_ds_profiles.refresh_from_db()
    assert user_not_in_ds_profiles.ds_id == ""


@pytest.mark.django_db(transaction=True)
def test_associate_or_update_ds_profile_to_users_async_task():
    CollegueFactory.create_batch(3)

    user_ids_qs = Collegue.objects.values_list("id", flat=True)
    assert user_ids_qs.count() == 3

    with pytest.raises(kombu.exceptions.EncodeError):
        associate_or_update_ds_profile_to_users.delay(user_ids_qs)

    with pytest.raises(kombu.exceptions.EncodeError):
        associate_or_update_ds_profile_to_users.delay(set(user_ids_qs))

    associate_or_update_ds_profile_to_users.delay(list(user_ids_qs))
