"""Local case-service facade for the Appeal runtime."""

from .approval_links import ApprovalLink, ApprovalLinkError, ApprovalLinkSigner
from .auth import AuthenticationError, FirebaseIdTokenVerifier, FirebasePrincipal, PrincipalVerifier
from .service import CaseNotFound, LocalAppealService, PersistedCaseView
from .http_api import LocalHttpApi
from .mcp_api import McpHttpApi

__all__ = [
    "ApprovalLink",
    "ApprovalLinkError",
    "ApprovalLinkSigner",
    "AuthenticationError",
    "CaseNotFound",
    "FirebaseIdTokenVerifier",
    "FirebasePrincipal",
    "LocalAppealService",
    "LocalHttpApi",
    "McpHttpApi",
    "PersistedCaseView",
    "PrincipalVerifier",
]
