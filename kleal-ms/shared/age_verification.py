"""Didit hosted 18+ boundary. Never persist provider payloads or log their contents.

The sqlite file contains only an opaque account binding, session ID, status, 18+
result and bounded security metadata. It is independent of self-declared profile
age/verified flags. All services must use the same path and rollout configuration.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import sqlite3
import time
import uuid
import age_proof
from contextlib import contextmanager
from contextvars import ContextVar
from urllib import request, error
from urllib.parse import urlsplit

PREFIX = '/api/onboarding/age-verification'
ACTIVE = {'Not Started', 'In Progress', 'Resubmitted', 'Awaiting User'}
STATUS = {'Not Started': 'pending', 'In Progress': 'pending', 'Resubmitted': 'pending',
          'Awaiting User': 'pending', 'In Review': 'review', 'Approved': 'approved',
          'Declined': 'declined', 'Expired': 'expired', 'Kyc Expired': 'expired',
          'Abandoned': 'cancelled', 'Not Finished': 'cancelled'}

_AUTHORIZATION = ContextVar('age_request_authorization', default=None)


@contextmanager
def authorization(check):
    """Revalidate the initiating request after waits; never persist its token."""
    token = _AUTHORIZATION.set(check)
    try:
        yield
    finally:
        _AUTHORIZATION.reset(token)


class VerificationError(Exception):
    def __init__(self, code, http=503):
        self.code, self.http = code, http
        super().__init__(code)  # only safe codes, never provider bodies


def enabled():
    return os.environ.get('KLEAL_AGE_GATE_ENABLED') == '1'


def voluntary():
    """ДОБРОВОЛЬНАЯ проверка (18.10.2026, решение Ивана): пройти Didit может любой вошедший с анкетой,
    и одобрение даёт галочку. Это НЕ рубильник допуска: enabled() по-прежнему решает, пускать ли только
    проверенных, и пока он выключен, поиск и вход никого не прячут (04.10 обязательная проверка
    опустошила поиск). Выключается только явным KLEAL_AGE_VOLUNTARY=0."""
    return os.environ.get('KLEAL_AGE_VOLUNTARY', '1') != '0'


def active():
    """Путь проверки у провайдера работает: обязательная проверка или добровольная."""
    return enabled() or voluntary()


def subject(key, account):
    secret = os.environ.get('KLEAL_AGE_BINDING_SECRET', '')
    if len(secret) < 32:
        raise VerificationError('configuration')
    # Account recreation must not inherit a deleted account's approval.
    value = str(key) + ':' + str(account.get('created', ''))
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def required(account):
    if not enabled():
        return False
    try:
        cutoff = int(os.environ['KLEAL_AGE_GATE_FROM'])
        created = int(account.get('created') or 0)
        if cutoff <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise VerificationError('configuration')
    # Explicit grandfather policy, not a claim that legacy users passed KYC.
    return not created or created >= cutoff


@contextmanager
def database():
    path = os.environ.get('KLEAL_AGE_DB', '')
    if not path or not os.path.isabs(path):
        raise VerificationError('configuration')
    conn = sqlite3.connect(path, timeout=12)
    conn.row_factory = sqlite3.Row
    try:
        os.chmod(path, 0o600)
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS verification (
            subject TEXT PRIMARY KEY, session_id TEXT UNIQUE, status TEXT NOT NULL,
            over18 INTEGER NOT NULL DEFAULT 0, event_time INTEGER NOT NULL DEFAULT 0,
            attempt_at INTEGER NOT NULL DEFAULT 0, checked_at INTEGER NOT NULL DEFAULT 0
          );
          CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, subject TEXT NOT NULL, received INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS deleted_subjects (
            subject TEXT PRIMARY KEY
          );
        ''')
        conn.execute('BEGIN IMMEDIATE')
        if 'provider_event_time' not in {r[1] for r in conn.execute('PRAGMA table_info(verification)')}:
            # Old event_time mixed provider and local clocks. Never migrate it as
            # provider evidence; revalidate old approvals with a signed event.
            conn.execute('ALTER TABLE verification ADD COLUMN provider_event_time INTEGER NOT NULL DEFAULT 0')
            conn.execute("UPDATE verification SET status=CASE WHEN over18=1 THEN 'review' ELSE status END,over18=0,checked_at=0")
        if 'approval_hold' not in {r[1] for r in conn.execute('PRAGMA table_info(verification)')}:
            conn.execute('ALTER TABLE verification ADD COLUMN approval_hold INTEGER NOT NULL DEFAULT 0')
            conn.execute("UPDATE verification SET approval_hold=1 WHERE status IN ('review','declined','expired','cancelled')")
        columns = {r[1] for r in conn.execute('PRAGMA table_info(verification)')}
        proof_columns = {'proof_policy_hash': "TEXT NOT NULL DEFAULT ''",
                         'proof_version': "TEXT NOT NULL DEFAULT ''",
                         'proof_config_hash': "TEXT NOT NULL DEFAULT ''",
                         'proof_kind': "TEXT NOT NULL DEFAULT ''",
                         'proof_reason': "TEXT NOT NULL DEFAULT ''",
                         'proof_attempt_hold': 'INTEGER NOT NULL DEFAULT 0'}
        if not set(proof_columns) <= columns:
            for name, declaration in proof_columns.items():
                if name not in columns:
                    conn.execute('ALTER TABLE verification ADD COLUMN ' + name + ' ' + declaration)
            conn.execute("UPDATE verification SET status='review',over18=0,approval_hold=1,"
                         "proof_reason='provenance_required',checked_at=0 WHERE over18=1")
        if 'generation' not in columns:
            conn.execute("ALTER TABLE verification ADD COLUMN generation TEXT NOT NULL DEFAULT ''")
            conn.execute('UPDATE verification SET generation=lower(hex(randomblob(16)))')
        # Rotate even for other local writers. Delete/reinsert cannot recreate
        # an earlier generation (ABA); no account or provider payload is stored.
        conn.execute('''CREATE TRIGGER IF NOT EXISTS verification_generation_insert
          AFTER INSERT ON verification BEGIN
            UPDATE verification SET generation=lower(hex(randomblob(16))) WHERE subject=NEW.subject;
          END''')
        conn.execute('''CREATE TRIGGER IF NOT EXISTS verification_generation_update
          AFTER UPDATE ON verification WHEN NEW.generation=OLD.generation BEGIN
            UPDATE verification SET generation=lower(hex(randomblob(16))) WHERE subject=NEW.subject;
          END''')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record(conn, sub):
    return conn.execute('SELECT * FROM verification WHERE subject=?', (sub,)).fetchone()


def _public(rec=None, *, legacy=False, onboarded=True, verified=False):
    status = 'legacy_exempt' if legacy else (rec['status'] if rec else 'not_started')
    admitted = legacy or verified
    if not legacy and status == 'approved' and not verified:
        status = 'review'
    return {'ok': True, 'status': status, 'over18': verified,
            'admitted': admitted, 'onboarded': onboarded,
            'sessionId': rec['session_id'] if rec else None,
            'canStart': onboarded and (status in ('not_started', 'cancelled', 'expired')
                                      or (status == 'pending' and bool(rec and rec['session_id']))),
            'retryAfter': max(0, rec['attempt_at'] + 60 - int(time.time())) if rec else 0}


def public(rec=None, *, legacy=False, onboarded=True):
    # Standalone helper; transaction paths use _public only after revalidation.
    return _public(rec, legacy=legacy, onboarded=onboarded,
                   verified=age_proof.admitted(rec) if rec else False)


def same_record(before, after):
    if before is None or after is None:
        return before is None and after is None
    return (before['subject'] == after['subject'] and before['session_id'] == after['session_id']
            and before['generation'] == after['generation'])


def present(key, account, rec, *, onboarded=True, url=None):
    # The slow provider observation occurs with no open SQLite transaction.
    verified = age_proof.admitted(rec) if rec else False
    with database() as conn:
        live = record(conn, subject(key, account))
        if live is not None or verified or _AUTHORIZATION.get() is not None:
            current_account(key, account, conn=conn)
        if not same_record(rec, live):
            return _public(live, onboarded=onboarded)
        verified = verified and age_proof.local_policy(live) is not None
        result = _public(live, onboarded=onboarded, verified=verified)
        if url and live is not None and live['status'] == 'pending':
            result['url'] = url
        return result


def state(key, account, onboarded=True):
    if not required(account):
        if not voluntary():
            return public(legacy=True, onboarded=onboarded)
        # Добровольно: показываем НАСТОЯЩЕЕ состояние проверки, но допуск остаётся прежним (admitted) —
        # проверка не обязательна, и её отсутствие ни от чего не отрезает.
        with database() as conn:
            rec = record(conn, subject(key, account))
        result = present(key, account, rec, onboarded=onboarded)
        result['admitted'] = True
        result['voluntary'] = True
        return result
    with database() as conn:
        rec = record(conn, subject(key, account))
    return present(key, account, rec, onboarded=onboarded)


def filter_candidates(rows):
    if not enabled():
        return rows
    import kleal_auth
    accounts = kleal_auth._accounts()
    out = []
    for row in rows:
        key = row.get('owner')
        # Ownerless pre-rollout/demo profiles are not retroactively enrolled.
        if not key:
            out.append(row)
            continue
        account = accounts.get(key)
        try:
            if account and state(key, account)['admitted']:
                out.append(row)
        except VerificationError:
            pass  # A deleted/recreated candidate must not fail the whole search.
    return out


def delete(key, account):
    # Called by the existing account deletion flow, not a second account writer.
    if not os.environ.get('KLEAL_AGE_DB'):
        return
    sub = subject(key, account)
    with database() as conn:
        conn.execute('DELETE FROM events WHERE subject=?', (sub,))
        conn.execute('DELETE FROM verification WHERE subject=?', (sub,))


def begin_delete(key, account):
    """Permanent account-deletion barrier, separate from evidence-only purge."""
    if not os.environ.get('KLEAL_AGE_DB'):
        return
    with database() as conn:
        sub = subject(key, account)
        # Opaque tombstone survives crashes/workers; no documents or session ID.
        conn.execute('INSERT OR IGNORE INTO deleted_subjects VALUES(?)', (sub,))
        conn.execute('DELETE FROM events WHERE subject=?', (sub,))
        conn.execute('DELETE FROM verification WHERE subject=?', (sub,))


def hosted_url(value):
    parsed = urlsplit(str(value or ''))
    if (parsed.scheme != 'https' or parsed.netloc != 'verify.didit.me'
            or not parsed.path or parsed.path.startswith('/u/')):
        raise VerificationError('provider_response')
    return value


def current_account(key, account, *, conn=None):
    # Recheck AFTER acquiring the DB lock: a request may have waited while the
    # account was deleted. Never recreate evidence for that stale auth snapshot.
    import kleal_auth
    live = kleal_auth._accounts().get(key)
    if (not isinstance(live, dict) or live.get('deleting')
            or live.get('created') != account.get('created')):
        raise VerificationError('sign_in_required', 401)
    if conn is not None and conn.execute('SELECT 1 FROM deleted_subjects WHERE subject=?',
                                        (subject(key, account),)).fetchone():
        raise VerificationError('sign_in_required', 401)
    check = _AUTHORIZATION.get()
    if check is not None:
        request_key, request_account = check()
        if request_key != key or request_account.get('created') != account.get('created'):
            raise VerificationError('sign_in_required', 401)


def bound_account(sub):
    # Webhooks have only an opaque binding, not a client-supplied account key.
    import kleal_auth
    for key, account in kleal_auth._accounts().items():
        if isinstance(account, dict) and not account.get('deleting') and subject(key, account) == sub:
            return key, {'created': account.get('created')}
    return None


def same_attempt(before, after):
    return (before is not None and after is not None
            and before['subject'] == after['subject'] and before['session_id'] == after['session_id']
            and before['attempt_at'] == after['attempt_at'])


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # never forward the API key to another host


def provider(method, path, body=None):
    key = os.environ.get('DIDIT_API_KEY', '')
    if not key:
        raise VerificationError('configuration')
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request('https://verification.didit.me/v3/' + path, data=data,
                          headers={'x-api-key': key, 'Content-Type': 'application/json'}, method=method)
    try:
        with request.build_opener(NoRedirect).open(req, timeout=8) as res:
            raw = res.read(2_000_001)
            if len(raw) > 2_000_000:
                raise VerificationError('provider_response')
            # Do not hash one interpretation of ambiguous duplicate-key JSON.
            result = json.loads(raw, object_pairs_hook=age_proof._pairs)
            if not isinstance(result, dict):
                raise VerificationError('provider_response')
            return result
    except error.HTTPError as exc:
        # Some provider versions report depleted quota as a 400/403 body rather
        # than 402. Inspect only in memory and expose a fixed code, never the body.
        try:
            failure = json.loads(exc.read(8192))
            reason = ' '.join(str(failure.get(k) or '') for k in ('code', 'error', 'detail')).lower()
        except (ValueError, AttributeError, OSError):
            reason = ''
        if 'insufficient' in reason and ('credit' in reason or 'balance' in reason):
            raise VerificationError('credits') from None
        raise VerificationError({402: 'credits', 429: 'rate_limit', 401: 'configuration',
                                 403: 'configuration'}.get(exc.code, 'service')) from None
    except (OSError, ValueError):
        raise VerificationError('service') from None


def workflow():
    try:
        return str(uuid.UUID(os.environ['DIDIT_WORKFLOW_ID']))
    except (KeyError, ValueError):
        raise VerificationError('configuration')


def callback_url():
    value = os.environ.get('DIDIT_CALLBACK_URL', '')
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        if (not value or any(ord(char) <= 32 or ord(char) == 127 for char in value)
                or parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path != PREFIX + '/callback'
                or parsed.port not in (None, 443)
                or host == 'localhost' or host.endswith(('.localhost', '.local'))):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError()
    except ValueError:
        raise VerificationError('configuration') from None
    return value


def webhook_secret():
    value = os.environ.get('DIDIT_WEBHOOK_SECRET', '')
    if not value.strip() or value != value.strip():
        raise VerificationError('configuration')
    return value


def binding(data, sub, sid, *, allow_missing_workflow=False):
    if not isinstance(data, dict):
        raise VerificationError('provider_response')
    if (data.get('session_id') != sid or data.get('vendor_data') != sub
            or (data.get('workflow_id') != workflow()
                and not (allow_missing_workflow and 'workflow_id' not in data))):
        raise VerificationError('session_mismatch', 403)
    # Sandbox approval must never become live admission by accident.
    if data.get('environment') != os.environ.get('DIDIT_ENVIRONMENT', 'live'):
        raise VerificationError('environment_mismatch', 403)


def assess_decision(data, *, attempt_at=None, until=None):
    if not isinstance(data, dict):
        return age_proof.Proof()
    status = STATUS.get(data.get('status'), 'review') if isinstance(data.get('status'), str) else 'review'
    if status != 'approved':
        return age_proof.Proof(status=status, reason='provider_status')
    return age_proof.evaluate(data, attempt_at=attempt_at, until=until)


def reduce_decision(data, *, attempt_at=None, until=None):
    proof = assess_decision(data, attempt_at=attempt_at, until=until)
    return proof.status, proof.over18


def decision_path(sid):
    # Expanded evidence is never requested without an explicitly reviewed local
    # contract. No attributes are enabled here; provider-side redaction is a gate.
    return 'session/' + sid + '/decision/' + ('?include=events' if age_proof.policies() else '')


def update(conn, sub, data, proof, event_time=None):
    rec = record(conn, sub)
    binding(data, sub, rec['session_id'])
    # Proof was computed outside SQL. A removed/changed local policy revokes it.
    if proof.over18 and not any(age_proof.digest(p) == proof.policy_hash for p in age_proof.policies()):
        proof = age_proof.Proof(reason='policy_unavailable')
    attempt_hold = (bool(rec['proof_attempt_hold']) or data.get('status') == 'Resubmitted'
                    or bool(isinstance(data.get('activity_reviews'), list) and data['activity_reviews']))
    if attempt_hold:
        proof = age_proof.Proof(reason='attempt_or_override')
    status, over18 = proof.status, proof.over18
    if event_time is None:
        # GET has no documented monotonic decision revision. A local observation
        # can never advance the provider clock or clear a restrictive result.
        if rec['approval_hold'] and status in ('approved', 'pending'):
            return
    elif event_time < rec['provider_event_time']:
        return  # superseded by a later SIGNED provider event, never by polling
    elif event_time == rec['provider_event_time']:
        # Didit event times have second precision. An ambiguous same-second
        # approval must never beat a restrictive result; revocation wins ties.
        if over18 or not rec['over18']:
            return
    hold = 0 if over18 and event_time is not None else int(bool(rec['approval_hold']) or status in ('review', 'declined', 'expired', 'cancelled'))
    if hold and status == 'pending':
        status = 'review'
    conn.execute('UPDATE verification SET status=?,over18=?,provider_event_time=?,checked_at=?,approval_hold=?,'
                 'proof_policy_hash=?,proof_version=?,proof_config_hash=?,proof_kind=?,proof_reason=?,proof_attempt_hold=? WHERE subject=?',
                 (status, int(over18), rec['provider_event_time'] if event_time is None else event_time,
                  int(time.time()), hold, proof.policy_hash, proof.version_id, proof.config_hash,
                  proof.kind, proof.reason, int(attempt_hold), sub))


def _refresh(key, account, *, resume=False):
    sub = subject(key, account)
    with database() as conn:
        current_account(key, account, conn=conn)
        rec = record(conn, sub)
        fetch = bool(rec and rec['session_id'] and (resume or time.time() - rec['checked_at'] >= 10))
        if fetch:
            # Claim throttle before I/O so independent workers do not stampede.
            conn.execute('UPDATE verification SET checked_at=? WHERE subject=?', (int(time.time()), sub))
            rec = record(conn, sub)
    if not fetch:
        return present(key, account, rec)
    data = provider('GET', decision_path(rec['session_id']))
    binding(data, sub, rec['session_id'])
    proof = assess_decision(data, attempt_at=rec['attempt_at'])
    url = hosted_url(data.get('session_url')) if resume and data.get('status') in ACTIVE else None
    with database() as conn:
        current_account(key, account, conn=conn)
        live = record(conn, sub)
        if not same_record(rec, live):
            return _public(live)  # Never apply an old poll over a revoke/delete.
        update(conn, sub, data, proof)
        rec = record(conn, sub)
    return present(key, account, rec, url=url)


def reconcile(key, account):
    return _refresh(key, account)


def start(key, account, language='en', onboarded=False):
    if not onboarded:
        raise VerificationError('onboarding_required', 409)
    if not required(account) and not voluntary():
        return public(legacy=True)
    sub = subject(key, account)
    with database() as conn:
        current_account(key, account, conn=conn)
        rec = record(conn, sub)
        existing = bool(rec and rec['status'] in ('approved', 'review', 'declined', 'pending'))
    if existing:
        if rec['status'] == 'pending' and rec['session_id']:
            return _refresh(key, account, resume=True)
        return present(key, account, rec)
    # Validate local setup before reserving an attempt or performing any I/O.
    policies = age_proof.policies()
    if not policies:
        raise VerificationError('configuration')
    callback = callback_url()
    webhook_secret()
    request_body = {'workflow_id': workflow(), 'vendor_data': sub,
                    'callback': callback, 'callback_method': 'both',
                    'language': language if language in ('ru', 'en', 'es') else 'en'}
    with database() as conn:
        current_account(key, account, conn=conn)
        live = record(conn, sub)
        if not same_record(rec, live):
            return _public(live)
        now = int(time.time())
        if rec and now - rec['attempt_at'] < 60:
            raise VerificationError('cooldown', 429)
        # Persist ownership before POST; other workers see pending, not a second
        # paid attempt. A crashed in-flight create needs operator reconciliation.
        conn.execute("INSERT INTO verification(subject,status,attempt_at) VALUES(?,'pending',?) "
                     "ON CONFLICT(subject) DO UPDATE SET status='pending',session_id=NULL,over18=0,attempt_at=excluded.attempt_at",
                     (sub, now))
        reserved = record(conn, sub)
    sent = False
    try:
        allowed = [p for p in policies if age_proof.workflow_current(p, fresh=True)]
        if not allowed:
            raise VerificationError('configuration')
        reviewed = {age_proof.digest(p) for p in allowed}
        with database() as conn:
            current_account(key, account, conn=conn)
            if not same_record(reserved, record(conn, sub)):
                return _public(record(conn, sub))
            if not reviewed.intersection(age_proof.digest(p) for p in age_proof.policies()):
                raise VerificationError('configuration')
        # Persist the uncertainty BEFORE dispatch; a killed process cannot make
        # the next worker issue another potentially paid create blindly.
        with database() as conn:
            current_account(key, account, conn=conn)
            if not same_record(reserved, record(conn, sub)):
                return _public(record(conn, sub))
            conn.execute("UPDATE verification SET proof_reason='create_outcome_unknown' WHERE subject=?", (sub,))
            reserved = record(conn, sub)
        sent = True
        data = provider('POST', 'session/', request_body)
        try:
            sid = str(uuid.UUID(data['session_id']))
        except (KeyError, ValueError, TypeError):
            raise VerificationError('provider_response')
        if data.get('vendor_data') != sub or data.get('workflow_id') != workflow():
            raise VerificationError('session_mismatch', 403)
        url = hosted_url(data.get('url'))
        with database() as conn:
            current_account(key, account, conn=conn)
            if not same_record(reserved, record(conn, sub)):
                return _public(record(conn, sub))
            if not reviewed.intersection(age_proof.digest(p) for p in age_proof.policies()):
                raise VerificationError('configuration')
            conn.execute("UPDATE verification SET session_id=?,status='pending',over18=0,event_time=0,"
                         "provider_event_time=0,approval_hold=0,checked_at=0,proof_policy_hash='',proof_version='',"
                         "proof_config_hash='',proof_kind='',proof_reason='',proof_attempt_hold=0 WHERE subject=?", (sid, sub))
            rec = record(conn, sub)
        return present(key, account, rec, url=url)
    except Exception as exc:
        with database() as conn:
            if same_record(reserved, record(conn, sub)):
                if not sent:
                    # Платный вызов не уходил (сбой на проверке настроек) — паузы «раз в минуту» нет: она
                    # бережёт от второй ПЛАТНОЙ сессии, а её не было. Возвращаем прежнее время попытки
                    # (18.10.2026: человек нажал ещё раз через 2 с и получил 429 вместо понятной ошибки).
                    conn.execute("UPDATE verification SET status='not_started',attempt_at=? WHERE subject=?",
                                 (rec['attempt_at'] if rec else 0, sub))
                elif isinstance(exc, VerificationError) and exc.code in ('credits', 'rate_limit'):
                    conn.execute("UPDATE verification SET status='not_started' WHERE subject=?", (sub,))
                # Once dispatched, timeout/malformed response/revocation is
                # uncertain. Keep pending without SID and canStart=false until
                # an operator reconciles the provider attempt, never retry POST.
        raise


def recover_creation(key, account, sid, expected_attempt):
    """Operator-only reconciliation; NOT exposed to client HTTP or callback.

    Operator must locate the single provider create for this binding/attempt.
    Only an identity-bound provider GET is accepted; it never grants admission.
    A subsequent fresh signed webhook must independently establish proof.
    """
    try:
        sid = str(uuid.UUID(sid))
    except (ValueError, TypeError, AttributeError):
        raise VerificationError('invalid_request', 400) from None
    sub = subject(key, account)
    with database() as conn:
        current_account(key, account, conn=conn)
        rec = record(conn, sub)
        if (not rec or rec['session_id'] or rec['status'] != 'pending'
                or rec['attempt_at'] != expected_attempt):
            raise VerificationError('state_changed', 409)
    data = provider('GET', decision_path(sid))
    binding(data, sub, sid)
    with database() as conn:
        current_account(key, account, conn=conn)
        if not same_record(rec, record(conn, sub)):
            raise VerificationError('state_changed', 409)
        conn.execute("UPDATE verification SET session_id=?,over18=0,approval_hold=1,"
                     "proof_policy_hash='',proof_version='',proof_config_hash='',proof_kind='',"
                     "proof_reason='create_recovered_requires_event',checked_at=0 WHERE subject=?", (sid, sub))
        # No URL, age claim or provider payload escapes this operation.
        return _public(record(conn, sub))


def canonical(data):
    # Didit's V2 canonical form also folds integral floats, including -0.0.
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return int(value) if isinstance(value, float) and value.is_integer() else value
    return json.dumps(normalize(data), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def webhook(raw, headers):
    secret = webhook_secret()

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError()
            value[key] = item
        return value

    try:
        data = json.loads(raw, object_pairs_hook=unique_pairs)
        timestamp = int(headers.get('X-Timestamp', ''))
        if type(data.get('timestamp')) is not int or data['timestamp'] != timestamp or abs(time.time() - timestamp) > 300:
            raise ValueError()
        expected = hmac.new(secret.encode(), canonical(data), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(headers.get('X-Signature-V2', ''))):
            raise ValueError()
        diagnostic = str(headers.get('X-Didit-Test-Webhook', '')).strip().lower() == 'true'
        # The Console's signed diagnostic omits event_id. It is stateless and
        # cannot approve an account; live deliveries still require a UUID.
        if 'event_id' in data or not diagnostic:
            event_id = str(uuid.UUID(data['event_id']))
        when = data['created_at']
        if type(when) is not int or when <= 0 or when > timestamp:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        raise VerificationError('invalid_webhook', 401) from None
    # Provider destination tests are diagnostics, never account evidence.
    # Authenticate before ACK; do not persist the event or call the provider.
    if diagnostic:
        return {'ok': True, 'ignored': True}
    if not active():
        # Transport diagnostics must not require activating the product gate.
        # Do not ACK/consume a real event during rollout or rollback: request a
        # retry and stop before any account lookup, database write or provider I/O.
        raise VerificationError('verification_disabled', 503)
    if data.get('webhook_type') not in ('status.updated', 'data.updated') or data.get('session_kind') == 'business':
        return {'ok': True, 'ignored': True}
    with database() as conn:
        rec = conn.execute('SELECT * FROM verification WHERE session_id=?', (data.get('session_id'),)).fetchone()
        if not rec:
            return {'ok': True, 'ignored': True}
        sub = rec['subject']
        binding(data, sub, rec['session_id'], allow_missing_workflow=True)
        digest = hashlib.sha256(event_id.encode()).hexdigest()
        if conn.execute('SELECT 1 FROM events WHERE id=?', (digest,)).fetchone():
            return {'ok': True, 'duplicate': True}
    account = bound_account(sub)
    if account is None:
        return {'ok': True, 'ignored': True}
    linear_clock = any(p.get('evidence_contract') == age_proof.LINEAR_KIND
                       for p in age_proof.policies())
    if linear_clock and data.get('status') not in ACTIVE and data.get('status') != 'Approved':
        # Observed HOSTED V3 deliveries retain session creation in created_at,
        # even for completion. A restrictive event uses signed dispatch time as
        # a conservative barrier. Retried approvals must NEVER use that clock.
        when = timestamp
    fetched = None
    if 'workflow_id' not in data or (data.get('status') == 'Approved' and age_proof.policies()):
        # No network call may hold the global verification writer lock.
        try:
            fetched = provider('GET', decision_path(rec['session_id']))
            binding(fetched, sub, rec['session_id'])
        except VerificationError:
            with database() as conn:
                current_account(*account, conn=conn)
                live = record(conn, sub)
                # Restrictive failure may invalidate this attempt, but cannot
                # recreate a deleted row or overwrite a replacement session.
                if same_attempt(rec, live) and when >= live['provider_event_time']:
                    conn.execute("UPDATE verification SET status='review',over18=0,approval_hold=1,checked_at=0,"
                                 "proof_policy_hash='',proof_version='',proof_config_hash='',proof_kind='',proof_reason='proof_fetch_failed',"
                                 "provider_event_time=MAX(provider_event_time,?) WHERE subject=?", (when, sub))
            raise
        data = {**data, 'workflow_id': fetched['workflow_id']}
        if data.get('status') == 'Approved' and fetched.get('status') != 'Approved':
            data['status'] = 'In Review'
    decision = fetched if fetched is not None else (data.get('decision') or {})
    if not isinstance(decision, dict):
        raise VerificationError('invalid_webhook', 400)
    # Envelope is authoritative for identity/status; nested data cannot replace it.
    merged = {**decision, **{k: data[k] for k in ('session_id', 'vendor_data', 'workflow_id', 'environment', 'status')}}
    proof = assess_decision(merged, attempt_at=rec['attempt_at'],
                            until=timestamp if linear_clock else when)
    if proof.over18 and proof.kind == age_proof.LINEAR_KIND:
        # Full authenticated proof has exactly one validated engine terminal.
        # Its occurrence time does not advance when Didit retries the webhook,
        # so an old approval cannot clear a newer restrictive delivery.
        when = next(e['sent_at'] // 1000 for e in merged['events']
                    if e['event_type'] == 'WORKFLOW_STATUS_NODE_REACHED')
    elif linear_clock and proof.status not in ('pending', 'not_started'):
        when = timestamp
    with database() as conn:
        current_account(*account, conn=conn)
        live = record(conn, sub)
        if not same_attempt(rec, live):
            return {'ok': True, 'ignored': True}
        if conn.execute('SELECT 1 FROM events WHERE id=?', (digest,)).fetchone():
            return {'ok': True, 'duplicate': True}
        if not same_record(rec, live) and proof.over18:
            # A raced approval must be retried from a new snapshot. Restrictive
            # signed events still reduce the current attempt in provider order.
            # Didit retries 5xx/404, not 409. Do not consume the event on this
            # transient generation race; its next delivery rechecks all proof.
            raise VerificationError('state_changed', 503)
        update(conn, sub, merged, proof, when)
        conn.execute('INSERT INTO events VALUES(?,?,?)', (digest, sub, int(time.time())))
        conn.execute('DELETE FROM events WHERE received<?', (int(time.time()) - 86400 * 30,))
    return {'ok': True}
