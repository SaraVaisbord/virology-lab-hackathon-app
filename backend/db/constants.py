"""Compatibility shim during the refactor — the vocabulary is domain/vocabulary.py. Removed in its last step."""

from domain.vocabulary import *  # noqa: F401,F403
from domain.vocabulary import label_keywords  # noqa: F401
