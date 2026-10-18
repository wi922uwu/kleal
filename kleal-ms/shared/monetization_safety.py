"""Защита destructive synthetic/rehearsal tools; не используется live commands."""
import ipaddress
import os
import re

LOOPBACK_HOSTS={'localhost','127.0.0.1','::1'}
OVERRIDE_ENV=('PGHOSTADDR','PGSERVICE','PGSERVICEFILE')


def _environment():
    if any(os.environ.get(key) for key in OVERRIDE_ENV):
        raise ValueError('test connection forbids hostaddr/service environment overrides')


def validate_test_dsn(dsn):
    """До соединения: никаких libpq service/hostaddr/multihost обходов URL guard."""
    from psycopg.conninfo import conninfo_to_dict
    _environment()
    parameters=conninfo_to_dict(dsn)
    if any(parameters.get(key) for key in ('hostaddr','service','servicefile')):
        raise ValueError('test connection forbids hostaddr/service overrides')
    if parameters.get('host') not in LOOPBACK_HOSTS or ',' in parameters.get('port',''):
        raise ValueError('explicit single loopback test endpoint required')
    if not re.fullmatch(r'kleal_monetization_test[a-z0-9_]*',parameters.get('dbname','')):
        raise ValueError('explicit test database required')
    return parameters


def guard(conn,*,require_schema=True):
    """Проверяет выбранный libpq peer (PQhostaddr), а не только label host.

    inet_server_addr() не определяет локальность клиента при Docker DNAT:
    адрес сервера внутри контейнера может быть private, а фактический endpoint
    клиента обязан быть loopback. Проверка выполняется до любой записи.
    """
    _environment()
    try:
        peer=ipaddress.ip_address(conn.info.hostaddr)
    except (ValueError,AttributeError,TypeError):
        raise ValueError('cannot establish actual loopback peer') from None
    if conn.info.host not in LOOPBACK_HOSTS or not peer.is_loopback:
        raise ValueError('actual loopback test endpoint required')
    database,schema=conn.execute('select current_database(),current_schema()').fetchone()
    if not re.fullmatch(r'kleal_monetization_test[a-z0-9_]*',database or ''):
        raise ValueError('test database required')
    if require_schema and not re.fullmatch(r'test_[a-z0-9_]+',schema or ''):
        raise ValueError('exact isolated test_* schema required')
