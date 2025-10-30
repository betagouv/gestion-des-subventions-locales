import logging

logger = logging.getLogger(__name__)


class DsServiceException(Exception):
    DEFAULT_MESSAGE = ""
    DEFAULT_LOG_LEVEL = logging.WARNING
    DEFAULT_LOG_MESSAGE = "DS service error"

    def __init__(self, message=None, level=None, log_message=None, extra=None, *args):
        if message is None:
            message = self.DEFAULT_MESSAGE

        if level is None:
            level = self.DEFAULT_LOG_LEVEL
        if log_message is None:
            log_message = self.DEFAULT_LOG_MESSAGE

        super().__init__(message, *args)

        logger.log(
            level,
            log_message or message,
            extra=extra,
            exc_info=self if level >= logging.ERROR else None,
            stack_info=level >= logging.ERROR,
        )


class DsConnectionError(DsServiceException):
    DEFAULT_MESSAGE = "Nous n'arrivons pas à nous connecter à Démarches Simplifiées."
    DEFAULT_LOG_MESSAGE = "DS connection error"


class InstructeurUnknown(DsServiceException):
    DEFAULT_MESSAGE = "Nous ne connaissons pas votre identifiant DS."
    DEFAULT_LOG_MESSAGE = "User does not have DS id"


class FieldError(DsServiceException):
    DEFAULT_MESSAGE = "Le champ n'existe pas dans la démarche."
    DEFAULT_LOG_LEVEL = logging.ERROR
    DEFAULT_LOG_MESSAGE = "Field not found in demarche"


class UserRightsError(DsServiceException):
    DEFAULT_MESSAGE = "Vous n'avez pas les droits suffisants pour modifier ce dossier."
    DEFAULT_LOG_LEVEL = logging.INFO
    DEFAULT_LOG_MESSAGE = "Instructeur has no rights on the dossier"
