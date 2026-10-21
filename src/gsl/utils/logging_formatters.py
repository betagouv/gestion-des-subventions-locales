import json
import logging

COLORS = {
    "DEBUG": "\033[90m",  # gris
    "INFO": "\033[94m",  # bleu
    "WARNING": "\033[93m",  # jaune
    "ERROR": "\033[91m",  # rouge
    "CRITICAL": "\033[95m",  # magenta
    "RESET": "\033[0m",
    "EXTRA": "\033[90m",  # gris clair pour les extras
}


class DynamicExtraFormatter(logging.Formatter):
    """
    Formatter qui affiche tous les champs 'extra' passés au logger,
    sans avoir à les déclarer dans le format.
    """

    def format(self, record):
        # Les attributs standards de LogRecord
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
            "taskName",
            "request",
        }

        # Trouver les attributs "extra"
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}

        # Formatter le message de base
        base = super().format(record)

        # Couleur du niveau
        color = COLORS.get(record.levelname, "")
        reset = COLORS["RESET"]

        # Colorer le message principal
        base_colored = f"{color}{base}{reset}"

        # Ajouter les extras, colorés aussi
        if extras:
            extras_str = json.dumps(extras, ensure_ascii=False)
            base_colored += f" {COLORS['EXTRA']}| extras: {extras_str}{reset}"

        return base_colored
