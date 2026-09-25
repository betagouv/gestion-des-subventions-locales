import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


@pytest.fixture
def stored():
    saved = []

    def save(name):
        saved.append(default_storage.save(name, ContentFile(b"x")))
        return saved[-1]

    yield save
    for name in saved:
        default_storage.delete(name)


def test_colliding_names_get_a_sequential_suffix(stored):
    assert stored("annexe/programmation_projet_1/plan.pdf").endswith("/plan.pdf")
    assert stored("annexe/programmation_projet_1/plan.pdf").endswith("/plan_2.pdf")
    assert stored("annexe/programmation_projet_1/plan.pdf").endswith("/plan_3.pdf")


def test_suffix_is_scoped_to_the_folder(stored):
    stored("annexe/programmation_projet_1/plan.pdf")

    assert stored("annexe/programmation_projet_2/plan.pdf").endswith("/plan.pdf")
