import os

from django.core.files.storage import InMemoryStorage
from storages.backends.s3 import S3Storage


class SequentialSuffixMixin:
    """Name a colliding upload `plan_2.pdf` rather than `plan_HxK3mQz.pdf`.

    Stored names are shown to users as-is. Django's random suffix exists
    because two concurrent uploads can settle on the same sequential name;
    that window here is two identically named files uploaded on the same
    programmation projet in the same instant.
    """

    def get_available_name(self, name, max_length=None):
        root, extension = os.path.splitext(name)
        counter = 1
        while self.exists(name):
            counter += 1
            name = f"{root}_{counter}{extension}"
        return super().get_available_name(name, max_length)


class MediaStorage(SequentialSuffixMixin, S3Storage):
    pass


class InMemoryMediaStorage(SequentialSuffixMixin, InMemoryStorage):
    """So tests run on the same naming rules as production."""
