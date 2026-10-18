FIELDS = {
    "first_name",
    "last_name",
    "id_number",
    "central_number",
    "received_date",
    "sender",
    "commitment_number",
}

MULTI_VALUE_FIELDS = {
    "central_number",
    "commitment_number",
}

FORM_STATUSES = {
    "uploaded",
    "processing",
    "extracted",
    "failed",
    "approved",
}

FIELD_STATUSES = {
    "unverified",
    "verified",
    "uncertain",
    "confirmed",
    "not_found",
}

FORM_TYPES = {
    "clalit",
    "maccabi",
    "meuhedet",
    "leumit",
    "hospital",
    "other",
}

SENDER_KINDS = {
    "health_fund",
    "hospital",
    "lab",
    "government",
    "military",
    "other",
}
