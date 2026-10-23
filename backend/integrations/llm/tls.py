"""TLS for the LLM providers' HTTP clients only — never for the whole process.

By default certificates are verified against the system / certifi CAs. Behind a filtering proxy that re-signs traffic
with its own certificate, point ca_bundle at that CA (PEM) instead of turning verification off.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass


@dataclass(frozen=True)
class TlsSettings:
    ca_bundle: str  # PEM file with the CA(s) to trust; "" = the default CAs
    insecure: bool  # LOCAL DEVELOPMENT ONLY: don't verify certificates (these clients only)


def ssl_context(tls: TlsSettings | None) -> ssl.SSLContext | None:
    """The SSL context for an LLM client, or None for the library's default (verify against the default CAs)."""
    if tls is None:
        return None
    if tls.insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if tls.ca_bundle:
        return ssl.create_default_context(cafile=tls.ca_bundle)
    return None
