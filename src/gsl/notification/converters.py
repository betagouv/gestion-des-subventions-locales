from gsl.notification.models import GeneratedDocument


class GeneratedDocumentTypeConverter:
    regex = "|".join(GeneratedDocument.Type.values)

    def to_python(self, value: str) -> GeneratedDocument.Type:
        return GeneratedDocument.Type(value)

    def to_url(self, value: str) -> str:
        return str(value)
