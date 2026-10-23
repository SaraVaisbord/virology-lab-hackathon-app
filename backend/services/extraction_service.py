"""Compatibility shim during the refactor — the pipeline is services/extraction_pipeline.py, the rules are
domain/verification.py and the command line is scripts/extract_forms.py. Removed in its last step."""

from __future__ import annotations

import config
from container import verification_rules as _rules
from domain.verification import build_fields, form_type_of, match_sender, sample_is_commitment_on  # noqa: F401
from services.extraction_pipeline import user_facing_error  # noqa: F401


def verification_rules():
    return _rules(config)


if __name__ == "__main__":
    from scripts.extract_forms import main

    main()
