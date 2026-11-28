# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which local account an SSO identity may sign in as (#18338).

Two rules, applied by ``SSOService._find_or_provision_user`` before any token is minted:

- **Eligibility.** The account must pass ``login_refusal``, the same rule password
  login applies (active, not deleted). There is one rule, not an SSO copy of it.
- **Linking an existing account by email.** An identity with no SSO link whose email
  matches an existing account is linked to it ONLY when all of these hold:
  the provider opts in (``config["link_existing_by_verified_email"] is True``), the
  identity provider asserted the email as verified (OIDC ``email_verified``), the
  account is not a platform admin, and -- for a provider bound to an organization --
  the account belongs to that same organization. Otherwise the login is refused and the account
  has to be linked explicitly. SAML and LDAP assert no verification claim, so they
  never link by email.

Before #18322 every SSO path raised before minting, so these rules close paths that
had never issued a token; no working login is taken away.
"""

from typing import Any

from autobot_shared.user_management.login_eligibility import login_refusal

#: Provider ``config`` key that opts in to linking an existing account by verified email.
LINK_POLICY_KEY = "link_existing_by_verified_email"


def asserted_email_verified(claims: dict[str, Any]) -> bool:
    """Whether OIDC *claims* assert the email as verified (``true``, or the string ``"true"``)."""
    value = claims.get("email_verified")
    return value is True or (isinstance(value, str) and value.lower() == "true")


def account_refusal(user: Any) -> str | None:
    """Why *user* may not be signed in to, or None. The password-login rule, reused."""
    return login_refusal(user)


def email_link_refusal(provider: Any, user_data: dict[str, Any], existing: Any) -> str | None:
    """Why an unlinked identity may not be linked to *existing* by email, or None."""
    if existing.is_platform_admin:
        return "an SSO identity is never linked to a platform admin by email"
    provider_org = getattr(provider, "org_id", None)
    if provider_org is not None and getattr(existing, "org_id", None) != provider_org:
        return "the account with this email belongs to another organization"
    if (provider.config or {}).get(LINK_POLICY_KEY) is not True:
        return "an account with this email exists; it must be linked explicitly"
    if user_data.get("email_verified") is not True:
        return "the identity provider did not assert the email as verified"
    return account_refusal(existing)
