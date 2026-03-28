"""Billing service — subscription gating for dealerships.

Pure Python, no I/O, no async, no DB imports.
All logic is stateless and testable without a database connection.
"""

from datetime import UTC, datetime

# Maps Lemon Squeezy subscription status strings to our internal status strings.
# Safe default for unknown values: "expired" (most restrictive).
LS_STATUS_MAP: dict[str, str] = {
    "on_trial": "trial",
    "active": "active",
    "past_due": "past_due",
    "paused": "past_due",
    "unpaid": "past_due",
    "cancelled": "cancelled",
    "expired": "expired",
}


def map_ls_status(ls_status: str) -> str:
    """Map a Lemon Squeezy status string to our internal status string.

    Returns "expired" for any unknown/future LS status values — the most
    restrictive safe default, ensuring we never accidentally grant access.
    """
    return LS_STATUS_MAP.get(ls_status, "expired")


def is_subscription_active(dealership) -> bool:
    """Return True if the dealership has an active subscription.

    Handles naive datetimes from SQLAlchemy (DateTime columns without
    timezone=True return naive datetimes). Normalizes them to UTC before
    comparison to avoid TypeError.

    Active states:
    - status == "active": fully paid and active
    - status == "trial": on trial (LS manages trial end date)
    - status == "past_due" with grace_period_ends_at in the future: grace period
    - status is None with trial_ends_at in the future: pre-subscription trial

    Inactive states:
    - dealership is None (orphaned lookup)
    - status == "cancelled" or "expired"
    - status == "past_due" with expired or missing grace period
    - status is None with no or expired trial_ends_at
    """
    if dealership is None:
        return False

    status = dealership.subscription_status

    if status in ("active", "trial"):
        return True

    if status == "past_due":
        gpe = dealership.grace_period_ends_at
        if gpe is None:
            return False
        now = datetime.now(UTC)
        if gpe.tzinfo is None:
            gpe = gpe.replace(tzinfo=UTC)
        return now < gpe

    if status is None:
        # D-19 exception: no subscription yet but trial_ends_at may be set
        tea = dealership.trial_ends_at
        if tea is None:
            return False
        now = datetime.now(UTC)
        if tea.tzinfo is None:
            tea = tea.replace(tzinfo=UTC)
        return now < tea

    # Catches "cancelled", "expired", and any other value
    return False
