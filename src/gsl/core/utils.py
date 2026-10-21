import re


def kebab_case(name: str) -> str:
    """CamelCase -> kebab-case, e.g. LettreRefusSignee -> lettre-refus-signee."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
