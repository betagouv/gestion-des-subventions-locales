from enum import StrEnum


class BulkAction(StrEnum):
    GENERATE_ACCEPTED = "generate_accepted"
    GENERATE_REFUS = "generate_refus"
    NOTIFY_REFUS = "notify_refus"
