"""LLM providers that read a page image into the extraction JSON (one shape for every provider).

Every provider implements base.LlmProvider and fails in one of the three ways in errors.py; router.LlmRouter
fails over between them in the configured order.
"""
