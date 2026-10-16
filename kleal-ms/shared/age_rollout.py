"""Server-owned 18+ rollout: exact canary keys or explicit all-account mode.

Only literal KLEAL_AGE_REQUIRE_ALL=1 enables all accounts. Missing/invalid cohort
configuration alone never enables a global rollout. Enrollment is not approval:
the same account-bound provider proof is required in both rollout modes.
No name, query/body value, IP, device field or frontend flag selects the cohort.
"""
import json
import os


def dev_demo_auth():
    """Explicit server-only dev opt-in; never an age or identity assertion.

    A shared demo account can carry a real Didit result, but its bearer holders
    are not thereby identified. Missing/typo/truthy aliases stay fail-safe.
    """
    return os.environ.get('KLEAL_DEV_KYC_DEMO_AUTH') == '1'


def requires_all():
    """Explicit operator opt-in, independent of the admission kill switch."""
    return os.environ.get('KLEAL_AGE_REQUIRE_ALL') == '1'


def configured_member(key):
    if not isinstance(key, str) or not key or key != key.strip() or key == '*':
        return False
    if requires_all():
        return True
    try:
        keys = json.loads(os.environ.get('KLEAL_AGE_COHORT_KEYS', '[]'))
        if (not isinstance(keys, list) or not keys or len(keys) > 10
                or any(not isinstance(k, str) or not k or k != k.strip() or k == '*' for k in keys)):
            return False
        return key in keys
    except (ValueError, TypeError):
        return False


def enrolled(key):
    return os.environ.get('KLEAL_AGE_GATE_ENABLED') == '1' and configured_member(key)


def delete_account(key, account):
    # Keep rollout scope configured until evidence is deleted, even with the
    # admission switch off. Non-enrolled canary accounts remain independent.
    if configured_member(key):
        import age_verification as age
        age.delete(key, account)


def begin_delete_account(key, account):
    if configured_member(key):
        import age_verification as age
        age.begin_delete(key, account)


def check_configuration():
    # Neither mode may exempt existing users based on their registration date.
    if os.environ.get('KLEAL_AGE_GATE_FROM') != '1':
        from age_verification import VerificationError
        raise VerificationError('configuration')


def filter_candidates(rows):
    # In all-account mode an ownerless/legacy row has no verifiable account.
    # Canary mode retains unrelated rows and their original ordering.
    all_active = requires_all() and os.environ.get('KLEAL_AGE_GATE_ENABLED') == '1'
    if not all_active and not any(enrolled(row.get('owner')) for row in rows):
        return rows
    import age_verification as age
    import kleal_auth
    accounts = kleal_auth._accounts()
    visible = []
    for row in rows:
        key = row.get('owner')
        if not enrolled(key):
            if not all_active:
                visible.append(row)
            continue
        try:
            check_configuration()
            if key in accounts and age.state(key, accounts[key])['admitted']:
                visible.append(row)
        except Exception:
            pass  # only the enrolled row stays hidden; no PII/error-body logging
    return visible
