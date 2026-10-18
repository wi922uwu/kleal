"""Только subprocess regression: deterministic ranking, реальный entrypoint/worker/PG."""
import os
import inspect
from pathlib import Path
import runpy
import monetization_commands as commands
import monetization_safety as safety

safety.validate_test_dsn(os.environ['KLEAL_MONETIZATION_TEST_DSN'])
with commands.ms.connection() as conn:
    safety.guard(conn)
    if any(row[0] not in ('a','b','c','d') for row in conn.execute('select owner_id from monetization_accounts')):
        raise ValueError('synthetic owners only')
folder=Path(os.environ['SYNTHETIC_STARTUP_MEDIA']).resolve()
if not folder.is_dir() or not folder.name.startswith('kleal_monetization_fixture_'):
    raise ValueError('disposable synthetic media directory required')
original=commands.install
complete=commands.complete_launch
def traced(*args,**kwargs):
    try:return complete(*args,**kwargs)
    except Exception:
        import traceback
        traceback.print_exc()
        raise
commands.complete_launch=traced
def install(namespace):
    original(namespace)
    namespace['_warm_up']=lambda:None
    namespace['load_candidates']=lambda:[]
    namespace['_people_index']=lambda **kw:{'by_id':{},'by_name':{}}
    namespace['render_search']=lambda *a,**kw:{'candidates':[]}
    namespace['VOICE_DIR']=str(folder)
commands.install=install


def entrypoint(path):
    """Mutation probes alter only this disposable subprocess's loaded source."""
    mutation=os.environ.get('SYNTHETIC_STARTUP_MUTATION','')
    if mutation=='without_cleanup':
        source=inspect.getsource(commands.start_launch_worker)
        line='                drain_cleanup()\n'
        assert source.count(line)==1
        exec(compile(source.replace(line,''),commands.__file__,'exec'),commands.__dict__)
    elif mutation=='without_start':
        source=Path(path).read_text()
        line='    monetization_commands.start_launch_worker()\n'
        assert source.count(line)==1
        exec(compile(source.replace(line,''),path,'exec'),{'__name__':'__main__','__file__':path})
        return
    elif mutation:
        raise ValueError('unknown startup mutation')
    runpy.run_path(path,run_name='__main__')
