"""Stateless payer-side determination boundary.

The service accepts only tenant/case identifiers and reference-only evidence
observations. It owns a private criterion copy and has no case store,
submission gate, chart reader, or external mutation client.
"""

from .http_api import PayerHttpApi
from .service import PayerService, PayerServiceRequestError

__all__ = ["PayerHttpApi", "PayerService", "PayerServiceRequestError"]
