import io

from gsl_notification.utils import (
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)


def test_update_file_name_to_put_it_in_a_programmation_projet_folder():
    # Simulate a file-like object with a 'name' attribute
    class DummyFile(io.BytesIO):
        def __init__(self, name):
            super().__init__()
            self.name = name

    file = DummyFile("document.pdf")
    programmation_projet_id = 42

    update_file_name_to_put_it_in_a_programmation_projet_folder(
        file, programmation_projet_id
    )

    assert file.name == "programmation_projet_42/document.pdf"
