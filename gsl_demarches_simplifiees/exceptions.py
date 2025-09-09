class DsServiceException(Exception):
    DEFAULT_MESSAGE = ""

    def __init__(self, message=None, *args):
        if message is None:
            message = self.DEFAULT_MESSAGE
        super().__init__(message, *args)


class InstructeurUnknown(DsServiceException):
    DEFAULT_MESSAGE = "L'instructeur n'a pas d'id DS."


class FieldError(DsServiceException):
    DEFAULT_MESSAGE = "Le champs n'existe pas dans la démarche."


class UserRightsError(DsServiceException):
    DEFAULT_MESSAGE = "Vous n'avez pas les droits suffisants pour modifier ce champs."
