"""Compatibility shim during the refactor — validators are domain/validators.py. Removed in its last step."""

from domain.validators import *  # noqa: F401,F403
