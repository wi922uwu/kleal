"""Small HTTP adapter; callback is navigation only, never an approval channel."""
import json
from urllib.parse import urlsplit, unquote
import age_verification as age
import age_rollout
import kleal_auth
from http_util import send_json, send


# Крючки службы, которая держит строки людей (онбординг ставит их при импорте), 18.10.2026:
#   ON_VERIFIED(key, method)  — одобрение увидено: поставить галочку verified в строке человека;
#   TEST_PASS(key, on)        — тестовый автопроход: поставить или снять галочку с пометкой «test»;
#   TEST_STATE(key) -> bool   — стоит ли сейчас тестовая галочка.
# Без крючков всё работает как раньше, просто без галочки. Ошибка крючка не ломает ответ.
ON_VERIFIED = None
TEST_PASS = None
TEST_STATE = None


def _hook(fn, *args):
    try:
        return fn(*args) if fn else None
    except Exception:
        return None


def identity(handler):
    key = kleal_auth.owner_key(handler)
    account = (kleal_auth._accounts() or {}).get(key)
    if not key or not isinstance(account, dict):
        raise age.VerificationError('sign_in_required', 401)
    return key, account


def path_of(handler):
    return unquote(urlsplit(getattr(handler, 'path', '')).path).rstrip('/')


def gate(handler):
    """Applied in gateway AND direct product services, not just client navigation."""
    if not age.enabled() or handler.command == 'OPTIONS':
        return False
    # Preserve the live product/auth behavior for everyone outside the explicit
    # canary. The existing handlers still enforce their own session ownership.
    if not age_rollout.enrolled(kleal_auth.owner_key(handler)):
        return False
    path = path_of(handler)
    # Buddy also exposes /buddy/* and bare /chat, /state, /launch, etc.
    # Its real bootstrap opts in so every alias is gated before body parsing.
    buddy_direct = getattr(handler.server, 'age_gate_service', None) == 'buddy'
    if not buddy_direct and not any(path == root or path.startswith(root + '/')
                                   for root in ('/api/agent', '/api/buddy', '/buddy')):
        return False
    try:
        key, account = identity(handler)
        age_rollout.check_configuration()
        # app/chat.tsx uses this one bounded profile-setup operation BEFORE the
        # profile is saved. Do not deadlock onboarding, or exempt general chat.
        setup_path = path in ('/api/buddy/interests-chat', '/buddy/interests-chat') or (buddy_direct and path == '/interests-chat')
        if handler.command == 'POST' and setup_path and not kleal_auth.caller_name(handler, strict_storage=True):
            return False
        if not age.state(key, account)['admitted']:
            raise age.VerificationError('age_verification_required', 403)
    except age.VerificationError as exc:
        handler.close_connection = True  # rejected POST body is deliberately not consumed
        send_json(handler, exc.http, {'ok': False, 'error': exc.code})
        return True
    except Exception:
        handler.close_connection = True
        send_json(handler, 503, {'ok': False, 'error': 'verification_unavailable'})
        return True
    return False


def handle(handler):
    # ContextVar is request/thread-scoped, including keep-alive. A revoked token
    # cannot authorize a provider POST or hosted URL after a slow workflow GET.
    protected = path_of(handler) in {age.PREFIX + '/' + leaf
                                     for leaf in ('status', 'refresh', 'session')}
    if protected:
        with age.authorization(lambda: identity(handler)):
            return _handle(handler)
    return _handle(handler)


def _handle(handler):
    path = path_of(handler)
    if handler.command == 'OPTIONS' or not path.startswith(age.PREFIX + '/'):
        return False
    handler.close_connection = True
    try:
        if path == age.PREFIX + '/callback' and handler.command == 'GET':
            # Fixed link; ignore ALL query fields, return targets and reported outcomes.
            body = ('<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
                 '<meta name="viewport" content="width=device-width, initial-scale=1">'
                 '<title>Kleal — return to app</title><h1>Вернитесь в Kleal</h1>'
                 '<p>Вручную переключитесь обратно в Expo Go и откройте Kleal. '
                 'Статус обновится с сервера. Если нет — нажмите «Проверить статус».</p>'
                 '<p>Return manually to Kleal in Expo Go. If the status does not update, tap Check status.</p>'
                 '<p>Vuelve manualmente a Kleal en Expo Go. Si el estado no se actualiza, pulsa Consultar estado.</p>'
                 '<p>Эта страница не подтверждает 18+. Доступ открывает только сервер Kleal.</p>'
                 '<p>This page does not approve verification. Only the Kleal server can grant access.</p>'
                 '<p>Optional, for the standalone Kleal app only (not Expo Go): '
                 '<a href="kleal://age-verification">Open Kleal</a></p>').encode('utf-8')
            handler.send_response(200)
            for key, value in {'Content-Type': 'text/html; charset=utf-8',
                               'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                               'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
                               'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"}.items():
                handler.send_header(key, value)
            handler.end_headers()
            handler.wfile.write(body)
            return True
        if path == age.PREFIX + '/enrollment' and handler.command == 'GET':
            key, account = identity(handler)
            send_json(handler, 200, {'ok': True, 'required': age_rollout.enrolled(key),
                                     'voluntary': age.voluntary(),
                                     # Кнопка «пройти автоматически» — только в тестовом режиме.
                                     'testPass': age_rollout.dev_demo_auth()})
            return True
        if path == age.PREFIX + '/test-pass' and handler.command == 'POST':
            # ТЕСТОВЫЙ АВТОПРОХОД для тестировщиков (Иван, 18.10.2026): без документов, только при
            # KLEAL_DEV_KYC_DEMO_AUTH=1. Ставит галочку с пометкой «test» и НЕ пишет в базу проверок —
            # настоящим 18+ для фильтра допуска не считается. {"undo": true} снимает её.
            if not age_rollout.dev_demo_auth():
                raise age.VerificationError('not_found', 404)
            key, account = identity(handler)
            size = int(handler.headers.get('Content-Length', '0') or 0)
            body = json.loads(handler.rfile.read(size)) if 0 < size <= 2048 else {}
            undo = bool(isinstance(body, dict) and body.get('undo'))
            if TEST_PASS is None or _hook(TEST_PASS, key, not undo) is not True:
                raise age.VerificationError('service')
            send_json(handler, 200, {'ok': True, 'status': 'not_started' if undo else 'approved',
                                     'over18': not undo, 'method': None if undo else 'test',
                                     'testPass': True})
            return True
        if path == age.PREFIX + '/webhook':
            # Provider transport is authenticated by HMAC, not a user's bearer.
            # A signed diagnostic can validate delivery before enrollment starts;
            # age.webhook refuses every real event while enforcement is disabled.
            if handler.command != 'POST':
                raise age.VerificationError('not_found', 404)
            size = int(handler.headers.get('Content-Length', '0'))
            if size <= 0 or size > 2_000_000:
                raise age.VerificationError('invalid_webhook', 413)
            result = age.webhook(handler.rfile.read(size), handler.headers)
            send_json(handler, 200, result)
            return True
        if path in (age.PREFIX + '/status', age.PREFIX + '/refresh', age.PREFIX + '/session'):
            key, account = identity(handler)
            if not age_rollout.enrolled(key):
                if (handler.command, path.rsplit('/', 1)[-1]) not in {('GET', 'status'), ('POST', 'refresh'), ('POST', 'session')}:
                    raise age.VerificationError('not_found', 404)
                if not age.voluntary():
                    send_json(handler, 200, age.public(legacy=True, onboarded=bool(kleal_auth.caller_name(handler))))
                    return True
                # Добровольная проверка: дальше обычный путь провайдера, без условий пробной группы.
            else:
                age_rollout.check_configuration()
        if not age.active():
            # GET status remains compatible before rollout, but never creates a session.
            identity(handler)
            if path == age.PREFIX + '/status' and handler.command == 'GET':
                send_json(handler, 200, age.public(legacy=True))
                return True
            raise age.VerificationError('configuration')
        else:
            key, account = identity(handler)
            onboarded = bool(kleal_auth.caller_name(handler, strict_storage=True))
            if path == age.PREFIX + '/status' and handler.command == 'GET':
                result = age.state(key, account, onboarded)
            elif path == age.PREFIX + '/refresh' and handler.command == 'POST':
                result = (age.reconcile(key, account) if (age.required(account) or age.voluntary())
                          else age.public(legacy=True))
                result['onboarded'] = onboarded
                result['canStart'] = bool(result['canStart'] and onboarded)
            elif path == age.PREFIX + '/session' and handler.command == 'POST':
                size = int(handler.headers.get('Content-Length', '0'))
                if size <= 0 or size > 2048:
                    raise age.VerificationError('invalid_request', 400)
                body = json.loads(handler.rfile.read(size))
                if not isinstance(body, dict) or set(body) - {'language'}:
                    raise age.VerificationError('invalid_request', 400)
                result = age.start(key, account, body.get('language'), onboarded)
            else:
                raise age.VerificationError('not_found', 404)
            # Presentation metadata only. Enrollment, authenticated key, provider
            # proof and admission above are identical in development mode.
            if age_rollout.dev_demo_auth():
                result['developmentDemo'] = True
                result['testPass'] = True
            if result.get('over18') and result.get('status') == 'approved':
                _hook(ON_VERIFIED, key, 'didit')     # настоящее одобрение -> галочка в строке
                result['method'] = 'didit'
            elif (age_rollout.dev_demo_auth() and result.get('status') in ('not_started', 'cancelled', 'expired', 'legacy_exempt')
                  and _hook(TEST_STATE, key) is True):
                # Тестовая галочка поверх «не начато»: показываем как пройденную, но с пометкой.
                result.update({'status': 'approved', 'over18': True, 'method': 'test'})
        send_json(handler, 200, result)
    except age.VerificationError as exc:
        # Код и ручка — в журнал (18.10.2026: «не получилось начать» не оставляло следа). Только код
        # ошибки и последний сегмент пути: ни ключей, ни тел провайдера, ни данных человека.
        print('[age] %s %s -> %s %s' % (handler.command, path.rsplit('/', 1)[-1], exc.http, exc.code), flush=True)
        send_json(handler, exc.http, {'ok': False, 'error': exc.code})
    except (ValueError, TypeError):
        send_json(handler, 400, {'ok': False, 'error': 'invalid_request'})
    except Exception:
        # Do not print provider exceptions (they can include PII, URL tokens or keys).
        send_json(handler, 503, {'ok': False, 'error': 'service'})
    return True
