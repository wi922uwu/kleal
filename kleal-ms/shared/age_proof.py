"""Narrow Didit proof adapter. No active policy is shipped with the application.

Policy assertions below are SERVER review attestations, not Didit response fields.
Contracts are versioned: routing proof and reviewed linear Determine workflows.
The latter trusts the provider's feature verdicts under a reviewed configuration,
not fictional duplicate-search branch events. Empty matches are not proof.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
import hashlib
import json
import os
import re
import stat
import time
import uuid

KIND = 'didit-first-attempt-routing-v1'
LINEAR_KIND = 'didit-linear-determine-v1'
FEATURES = ('id_verifications', 'liveness_checks', 'face_matches')
ASSERTIONS = {'complete_current_attempt_timeline', 'manual_changes_visible',
              'positive_duplicate_execution', 'duplicate_population_reviewed',
              'response_minimization_reviewed'}
LINEAR_ASSERTIONS = (ASSERTIONS - {'positive_duplicate_execution'}) | {
    'linear_graph_reviewed', 'no_feature_status_overrides',
    'document_duplicate_action_restrictive', 'face_search_enabled',
    'face_duplicate_action_restrictive', 'telemetry_types_reviewed'}
POLICY_KEYS = {'workflow_id', 'workflow_version_id', 'workflow_version', 'environment',
               'config_sha256', 'review_reference', 'reviewed', 'evidence_contract',
               'features', 'branches', 'terminal_node_id', 'assertions'}
BRANCH_KEYS = {'node_id', 'matched_branch_id', 'next_node_id', 'purpose'}
_request_config = ContextVar('didit_request_config', default=None)


@contextmanager
def request_scope():
    """Deduplicate only configuration reads, never account/session decisions."""
    token = _request_config.set({})
    try:
        yield
    finally:
        _request_config.reset(token)


@dataclass(frozen=True)
class Proof:
    status: str = 'review'
    over18: bool = False
    reason: str = 'proof_unavailable'
    policy_hash: str = ''
    version_id: str = ''
    config_hash: str = ''
    kind: str = ''


def _uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _name(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value) is not None


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def digest(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_policy_key')
        result[key] = value
    return result


def _valid(policy):
    if not isinstance(policy, dict):
        return False
    linear = policy.get('evidence_contract') == LINEAR_KIND
    keys = POLICY_KEYS | {'telemetry_event_types'} if linear else POLICY_KEYS
    if set(policy) != keys:
        return False
    if not all(_uuid(policy[k]) for k in ('workflow_id', 'workflow_version_id')):
        return False
    if (type(policy['workflow_version']) is not int or policy['workflow_version'] < 1
            or policy['environment'] not in ('sandbox', 'live') or policy['reviewed'] is not True
            or policy['evidence_contract'] not in (KIND, LINEAR_KIND) or not _hash(policy['config_sha256'])
            or not _name(policy['review_reference']) or not _name(policy['terminal_node_id'])):
        return False
    facts = policy['assertions']
    required = LINEAR_ASSERTIONS if linear else ASSERTIONS
    if not isinstance(facts, dict) or set(facts) != required or any(v is not True for v in facts.values()):
        return False
    features = policy['features']
    if (not isinstance(features, dict) or set(features) != set(FEATURES)
            or not all(_name(v) for v in features.values()) or len(set(features.values())) != 3):
        return False
    branches = policy['branches']
    if linear:
        telemetry = policy['telemetry_event_types']
        return (branches == [] and isinstance(telemetry, list) and len(telemetry) <= 64
                and all(_name(t) and not t.startswith('WORKFLOW_') for t in telemetry)
                and len(set(telemetry)) == len(telemetry))
    if not isinstance(branches, list) or not 2 <= len(branches) <= 16:
        return False
    for b in branches:
        if (not isinstance(b, dict) or set(b) != BRANCH_KEYS
                or not all(_name(b[k]) for k in ('node_id', 'matched_branch_id', 'next_node_id'))
                or b['purpose'] not in ('document_duplicates_clear', 'face_duplicates_clear', 'required_check')):
            return False
    purposes = [b['purpose'] for b in branches]
    return (purposes.count('document_duplicates_clear') == 1
            and purposes.count('face_duplicates_clear') == 1
            and len({b['node_id'] for b in branches}) == len(branches))


def policies():
    """Local allowlist only. Missing, unreviewed or malformed config denies all."""
    path = os.environ.get('DIDIT_REVIEWED_PROOF_POLICY', '')
    if not os.path.isabs(path):
        return []
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
                return []
            raw = source.read(65537)
        if len(raw) > 65536:
            return []
        data = json.loads(raw, object_pairs_hook=_pairs)
        if (not isinstance(data, dict) or set(data) != {'schema_version', 'policies'}
                or type(data['schema_version']) is not int or data['schema_version'] != 1
                or not isinstance(data['policies'], list) or len(data['policies']) > 16):
            return []
        rows = data['policies']
        if not all(_valid(p) for p in rows):
            return []
        ids = [(p['environment'], p['workflow_id'], p['workflow_version_id']) for p in rows]
        if len(set(ids)) != len(ids):
            return []
        return [p for p in rows if p['workflow_id'] == os.environ.get('DIDIT_WORKFLOW_ID')
                and p['environment'] == os.environ.get('DIDIT_ENVIRONMENT', 'live')]
    except (OSError, ValueError, TypeError, RecursionError):
        return []


def workflow_config_hash(snapshot):
    """Pin the entire GET Workflow response, including updated_at and unknown keys.

    This detects observed config drift, not a provider-attested execution snapshot.
    No fields are discarded and no response body is retained. Existing projection
    hashes fail closed and require a new human review using this exact recipe.
    """
    if (not isinstance(snapshot, dict)
            or not all(_uuid(snapshot.get(k)) for k in ('uuid', 'workflow_id'))
            or type(snapshot.get('version')) is not int or snapshot['version'] < 1
            or snapshot.get('status') != 'published' or snapshot.get('is_archived') is not False
            or not isinstance(snapshot.get('workflow_graph'), dict)
            or not isinstance(snapshot.get('response_attributes'), dict)
            or not isinstance(snapshot.get('updated_at'), str)):
        raise ValueError('workflow_configuration')
    revised = datetime.fromisoformat(snapshot['updated_at'].replace('Z', '+00:00'))
    if revised.utcoffset() is None:
        raise ValueError('workflow_configuration')
    raw = json.dumps(snapshot, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(b'didit-workflow-full-v1\n' + raw).hexdigest()


def _workflow_snapshot(version):
    from age_verification import provider
    return provider('GET', 'workflows/' + version + '/')


def workflow_current(policy, *, fresh=False):
    """One config observation per policy/request; writes force a fresh read.

    The server chooses the settings UUID from its local policy, never from a
    webhook/client claim. The existing provider transport is fixed-host, bounded
    and non-redirecting. A concurrent/unobserved provider mutation remains an
    activation blocker until immutable execution config or write control is proven.
    """
    from age_verification import VerificationError
    memo = _request_config.get()
    key = (digest(policy), os.environ.get('DIDIT_WORKFLOW_ID'),
           os.environ.get('DIDIT_ENVIRONMENT', 'live'),
           hashlib.sha256(os.environ.get('DIDIT_API_KEY', '').encode()).hexdigest())
    if memo is not None:
        if not fresh and key in memo:
            return memo[key]
        # A failed or interrupted forced refresh must invalidate prior success.
        memo[key] = False
    try:
        snapshot = _workflow_snapshot(policy['workflow_version_id'])
        result = (snapshot.get('uuid') == policy['workflow_version_id']
                and snapshot.get('workflow_id') == policy['workflow_id']
                and type(snapshot.get('version')) is int
                and snapshot['version'] == policy['workflow_version']
                and workflow_config_hash(snapshot) == policy['config_sha256'])
    except (VerificationError, OSError, ValueError, TypeError, AttributeError, RecursionError):
        result = False
    if memo is not None:
        memo[key] = result
    return result


def local_policy(rec):
    """Pure local provenance check, also repeated at SQL commit boundaries."""
    if not rec or not rec['over18'] or rec['status'] != 'approved':
        return None
    if not {'proof_policy_hash', 'proof_version', 'proof_config_hash', 'proof_kind',
            'proof_attempt_hold'} <= set(rec.keys()) or rec['proof_attempt_hold']:
        return None
    return next((p for p in policies() if rec['proof_policy_hash'] == digest(p)
                 and rec['proof_version'] == p['workflow_version_id']
                 and rec['proof_config_hash'] == p['config_sha256']
                 and rec['proof_kind'] == p['evidence_contract']), None)


def admitted(rec):
    """Policy removal/change revokes stored booleans, including across restart."""
    policy = local_policy(rec)
    return policy is not None and workflow_current(policy)


def _linear_terminal(events, policy, attempt_at, ceiling):
    """Select engine outcome, not the last UI event. Unknown telemetry denies.

    Non-routing type names require review from a real response before allowlisting;
    the public contract does not enumerate them. Never guess them here. The policy
    attests that these types cannot represent manual changes or resubmission.
    """
    if not isinstance(events, list) or not 1 <= len(events) <= 4096:
        return None
    terminal = None
    for event in events:
        if not isinstance(event, dict):
            return None
        sent = event.get('sent_at')
        if type(sent) is not int or not attempt_at * 1000 <= sent < (ceiling + 1) * 1000:
            return None
        kind = event.get('event_type')
        # Real HOSTED receipts use explicit null for SESSION_CREATED metadata.
        # It is not verification evidence; only this reviewed telemetry shape
        # may omit details. Missing keys and malformed/unknown events still deny.
        nullable_creation = (kind == 'SESSION_CREATED' and 'details' in event
                             and event['details'] is None)
        if not isinstance(event.get('details'), dict) and not nullable_creation:
            return None
        if kind == 'WORKFLOW_STATUS_NODE_REACHED':
            if terminal is not None:
                return None  # repeated outcomes/retries need a new session
            terminal = event
        elif kind not in policy['telemetry_event_types']:
            return None
    return terminal


def _clear_blocklist(value):
    """Recognize the reviewed V5 shape; unknown or historical flags veto."""
    if value is False:
        return True  # legacy explicitly clear response
    if not isinstance(value, dict) or set(value) != {'id_document', 'face', 'phone', 'email'}:
        return False
    for name, detail in value.items():
        if detail is None and name in ('phone', 'email'):
            continue
        if (not isinstance(detail, dict) or set(detail) != {'is_blocklisted', 'blocklisted_at'}
                or detail['is_blocklisted'] is not False or detail['blocklisted_at'] is not None):
            return False
    return True


def evaluate(data, *, attempt_at=None, until=None):
    """Authenticated server report in; bounded decision/provenance out, never age."""
    if not isinstance(data, dict) or data.get('status') != 'Approved':
        return Proof()
    reports = [data.get(k) for k in FEATURES]
    if any(not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
           or rows[0].get('status') != 'Approved' for rows in reports):
        return Proof(reason='feature_evidence')
    value = reports[0][0].get('age')
    if type(value) is not int or not 0 <= value <= 125:
        return Proof(reason='age_unavailable')
    if value < 18:
        return Proof(status='declined', reason='underage')
    matched = [p for p in policies() if p['workflow_version_id'] == data.get('workflow_version_id')
               and p['workflow_id'] == data.get('workflow_id') and p['environment'] == data.get('environment')
               and type(data.get('workflow_version')) is int and p['workflow_version'] == data['workflow_version']]
    if len(matched) != 1:
        return Proof(reason='policy_unavailable')
    p = matched[0]
    if not workflow_current(p, fresh=True):
        return Proof(reason='workflow_configuration')
    if data.get('session_kind') not in (None, 'user') or data.get('session_type') != 'HOSTED' or data.get('api_service') is not None:
        return Proof(reason='session_evidence')
    # Blocklist details are not positive execution proof. Unreviewed shapes or
    # any flag must not be silently ignored just because the route looks good.
    if 'blocklisted' in data and not _clear_blocklist(data['blocklisted']):
        return Proof(reason='blocklist_evidence')
    if data.get('status_override') is not None:
        return Proof(reason='attempt_or_override')
    if data.get('activity_reviews') != []:
        return Proof(reason='attempt_or_override')
    for key, rows in zip(FEATURES, reports):
        if rows[0].get('node_id') != p['features'][key]:
            return Proof(reason='feature_node')
        # Optional disclosed matches can veto; null/empty never establish proof.
        matches = rows[0].get('matches')
        if matches is not None:
            if not isinstance(matches, list):
                return Proof(reason='duplicate_evidence')
            for match in matches:
                if (not isinstance(match, dict) or not data.get('vendor_data')
                        or match.get('vendor_data') != data['vendor_data']
                        or match.get('status') != 'Approved' or match.get('is_blocklisted') is not False):
                    return Proof(reason='duplicate_evidence')
    if type(attempt_at) is not int or attempt_at <= 0:
        return Proof(reason='attempt_unavailable')
    if until is not None and type(until) is not int:
        return Proof(reason='attempt_unavailable')
    ceiling = int(time.time()) if until is None else min(int(time.time()), until)
    if type(ceiling) is not int or ceiling < attempt_at:
        return Proof(reason='attempt_unavailable')
    events = data.get('events')
    if p['evidence_contract'] == LINEAR_KIND:
        terminal = _linear_terminal(events, p, attempt_at, ceiling)
        if terminal is None:
            return Proof(reason='attempt_or_override')
        details = terminal['details']
        if (details.get('node_id') != p['terminal_node_id']
                or data.get('workflow_terminal_node_id') != p['terminal_node_id']
                or details.get('session_status') != 'Determine'
                or details.get('resolved_session_status') != 'Approved'
                or details.get('feature_statuses') != []):
            return Proof(reason='attempt_or_override')
        return Proof('approved', True, 'verified', digest(p), p['workflow_version_id'],
                     p['config_sha256'], LINEAR_KIND)
    # First-attempt-only contract. Extra/unknown steps cannot be ignored until
    # their meaning is documented and separately reviewed; no resubmit bypass.
    if not isinstance(events, list) or len(events) != len(p['branches']) + 1:
        return Proof(reason='attempt_or_override')
    previous = attempt_at * 1000 - 1
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('details'), dict):
            return Proof(reason='attempt_or_override')
        sent = event.get('sent_at')
        if type(sent) is not int or not previous < sent < (ceiling + 1) * 1000:
            return Proof(reason='attempt_or_override')
        previous = sent
    for actual, expected in zip(events[:-1], p['branches']):
        details = actual['details']
        if (actual.get('event_type') != 'WORKFLOW_BRANCH_EVALUATED' or details.get('fallback') is not False
                or any(details.get(k) != expected[k] for k in ('node_id', 'matched_branch_id', 'next_node_id'))):
            return Proof(reason='duplicate_execution')
    terminal = events[-1]
    details = terminal['details']
    if (terminal.get('event_type') != 'WORKFLOW_STATUS_NODE_REACHED'
            or details.get('node_id') != p['terminal_node_id']
            or data.get('workflow_terminal_node_id') != p['terminal_node_id']
            or details.get('session_status') != 'Approved' or details.get('resolved_session_status') != 'Approved'
            or details.get('feature_statuses') != []):
        return Proof(reason='attempt_or_override')
    return Proof('approved', True, 'verified', digest(p), p['workflow_version_id'], p['config_sha256'], KIND)
