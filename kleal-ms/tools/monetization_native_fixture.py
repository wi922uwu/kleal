#!/usr/bin/env python3
"""Disposable loopback fixture for native QA, NOT production/auth/KYC evidence.

Real current-worktree matching/monetization commands and isolated PostgreSQL.
Synthetic authentication, admission, users and ranking. No live network services.
The inherited test setup rejects non-loopback/non-test databases before writes.
"""
import argparse
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_monetization_phase2 import LegacyAdapters,ms
import monetization_admin as admin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=7599)
    parser.add_argument('--smoke',action='store_true',help='wire-only self-test; exit and drop the fixture schema')
    args=parser.parse_args()
    LegacyAdapters.setUpClass()
    fixture=LegacyAdapters();fixture.setUp()
    app=fixture.app
    import kleal_auth
    import monetization_http
    users=[{'id':x,'owner':x,'name':'QA '+x.upper(),'age':25,'verified':True,'interests':['coffee'],'open':True}
           for x in ('a','b','c','d')]
    app.load_candidates=lambda:users;app._load_pool_rows=lambda:users;app._people_index(force=True)
    app.VOICE_DIR=str(Path(fixture.tmp.name)/'voice');app.VIDEO_DIR=str(Path(fixture.tmp.name)/'video')
    app.transcribe_remote=lambda *args:('','')
    app.parse_intent=lambda query:{'topics':['coffee'],'title':query,'mode':'offline','type':'social','time':'Tomorrow evening'}
    app.send_json=lambda h,status,obj:app._send_json_raw(h,obj.get('httpStatus',status) if isinstance(obj,dict) else status,app._humanize(obj))
    accounts={x:{'person_id':x,'sessions':{hashlib.sha256(('synthetic-'+x).encode()).hexdigest():{'exp':time.time()+7200}}}
              for x in ('a','b','c','d')}
    with ms.connection() as conn:
        for user in users:
            conn.execute('insert into users(id,name_key,name,row) values(%s,%s,%s,%s)',
                         (user['id'],user['id'],user['name'],json.dumps(user)))

    class H(app.H):
        def synthetic_owner(self):
            # Use the same hashed-session/expiry resolver as the real wire handlers,
            # against this fixture's patched accounts only. Never guess from body/name.
            owner=kleal_auth.owner_key(self)
            if owner in accounts: return owner
            app._send_json_raw(self,401,{'ok':False,'error':'sign_in_required'})
            return None

        def do_GET(self):
            if self.path=='/api/onboarding/age-verification/enrollment':
                if not self.synthetic_owner(): return
                # Synthetic un-enrolled fixture; not a production admission decision.
                return app._send_json_raw(self,200,{'ok':True,'required':False})
            if self.path=='/qa/state':
                with ms.connection() as conn: result=admin.status(conn)
                return app._send_json_raw(self,200,{'schema':fixture.schema,'users':result})
            if monetization_http.handle(self): return
            return super().do_GET()

        def do_POST(self):
            if self.path.startswith('/qa/'):
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}')
                owner=body.get('owner','a')
                if owner not in accounts: return app._send_json_raw(self,400,{'error':'synthetic_owner_required'})
                if self.path=='/qa/grant':
                    with ms.connection() as conn:
                        result=admin.command(conn,action='grant',owner=owner,expires=int(time.time())+300,
                            operator='native-fixture',reason='synthetic manual Plus',key='native-'+str(time.time_ns()),apply=True)
                elif self.path=='/qa/expire':
                    with ms.transaction() as tx:
                        tx.conn.execute('update monetization_accounts set eligible=false,preview_start=%s,preview_end=%s '
                                        'where owner_id=%s',(tx.now-1209601,tx.now-1,owner))
                        tx.conn.execute('update monetization_manual_grants set created=%s,expires=%s where owner_id=%s and revoked is null',
                                        (tx.now-10,tx.now-1,owner))
                        result=tx.status(owner)
                elif self.path=='/qa/maps':
                    result=[]
                    for index,mode in enumerate(('offline','online','hybrid')):
                        intent={'topics':['coffee'],'mode':mode,'title':'Native '+mode,'starts_at':time.time()+86400,
                            'lat':40.4168+index*.004,'lng':-3.7038,'address':'Synthetic Madrid venue','city':'Madrid',
                            'country':'Spain','originCountry':'ES'}
                        result.append(app.save_intent('QA D',intent,'Native '+mode,launched=True,owner_id='d',idem='native-map-'+mode))
                else: return app._send_json_raw(self,404,{'error':'unknown_fixture_action'})
                return app._send_json_raw(self,200,result)
            if monetization_http.handle(self): return
            if self.path.startswith(('/api/auth/','/api/onboarding/')):
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}')
                if self.path in ('/api/auth/code/request','/api/auth/code/verify'):
                    # OTP is the one pre-session path: its explicit synthetic login
                    # selects the account, even if an old bearer is still attached.
                    login=str(body.get('email') or body.get('login') or '').strip().lower()
                    owner=next((x for x in accounts if login in (x,x+'@example.test')),None)
                    if not owner: return app._send_json_raw(self,400,{'ok':False,'error':'synthetic_login_required'})
                else:
                    owner=self.synthetic_owner()
                    if not owner: return
                user=next(u for u in users if u['id']==owner)
                profile={**user,'city':'Madrid','country':'Spain','languages':{'comfortable':['English']},
                    'interests':{'explicit':['coffee']},'geo':{'coarseLat':40.4,'coarseLon':-3.7},
                    'permissions':{'useProfileForMatching':True}}
                if self.path.endswith('/code/request'):
                    return app.send_json(self,200,{'ok':True,'sent':True,'dev_code':'123456','resend_in':0})
                if self.path.endswith(('/code/verify','/session')):
                    return app.send_json(self,200,{'ok':True,'token':'synthetic-'+owner,'login':owner+'@example.test',
                        'email':owner+'@example.test','isNew':False,'hasProfile':True,'profile':profile})
                if self.path.endswith('/profile'): return app.send_json(self,200,{'user':user})
                return app.send_json(self,200,{'ok':True,'enabled':False})
            return super().do_POST()

    server=None;worker=None
    try:
        with patch.object(kleal_auth,'_accounts',return_value=accounts),patch.object(kleal_auth,'_population',return_value=users):
            server=ThreadingHTTPServer(('127.0.0.1',args.port),H)
            print('Synthetic fixture http://127.0.0.1:'+str(server.server_port)+' schema='+fixture.schema,flush=True)
            if not args.smoke:
                server.serve_forever()
            else:
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                def request(path,owner='a',body=None,expected=200):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
                    headers={'Content-Type':'application/json'}
                    if owner is not None: headers['Authorization']='Bearer synthetic-'+owner
                    conn.request('GET' if body is None else 'POST',path,
                        body=None if body is None else json.dumps(body),
                        headers=headers)
                    response=conn.getresponse();raw=response.read();conn.close()
                    assert response.status==expected,(path,response.status,raw)
                    return json.loads(raw)
                # Real wire identity after login/reload: body name/email cannot select an account.
                for owner,body in [('b',{'name':'QA B'}),('b',{'name':''}),('c',{'name':'QA C'}),
                                   ('b',{'name':'QA A','email':'a@example.test'})]:
                    user=request('/api/onboarding/profile',owner,body)['user']
                    # Matching's real wire serializer humanizes owner, keeping owner_id.
                    assert (user['id'],user['owner_id'],user['name'])==(owner,owner,'QA '+owner.upper()),user
                session=request('/api/auth/session','b',{'email':'a@example.test'})
                assert (session['token'],session['profile']['id'],session['profile']['owner_id'])==('synthetic-b','b','b'),session
                for owner in (None,'unknown'):
                    for path,body in [('/api/onboarding/profile',{'name':'QA A','email':'a@example.test'}),
                                      ('/api/auth/session',{}),('/api/onboarding/age-verification/enrollment',None),
                                      ('/api/onboarding/profile-update',{'name':'QA A'})]:
                        assert request(path,owner,body,401)['error']=='sign_in_required'
                expiry=accounts['c']['sessions'][hashlib.sha256(b'synthetic-c').hexdigest()]
                expiry['exp']=time.time()-1
                assert request('/api/onboarding/profile','c',{},401)['error']=='sign_in_required'
                expiry['exp']=time.time()+7200
                for owner in (None,'a'):
                    login=request('/api/auth/code/verify',owner,{'email':'b@example.test','code':'123456'})
                    assert (login['token'],login['profile']['id'],login['profile']['owner_id'])==('synthetic-b','b','b'),login
                assert request('/api/auth/code/verify','b',{'login':'b@example.test','code':'123456'})['profile']['id']=='b'
                for body in ({'code':'123456'},{'email':'unknown@example.test','code':'123456'}):
                    assert request('/api/auth/code/verify','b',body,400)['error']=='synthetic_login_required'
                assert request('/api/auth/code/request',None,{'email':'b@example.test'})['sent'] is True
                print('PASS: synthetic profile/session bearer identity, explicit OTP login, missing/unknown/expired bearer denied',flush=True)
                request('/qa/expire',body={'owner':'a'})
                request('/qa/grant',body={'owner':'a'})
                a=request('/api/onboarding/monetization/v2/status')
                b=request('/api/onboarding/monetization/v2/status','b')
                assert a['plan']=='plus' and a['entitlementSources'][0]['source']=='manual'
                assert b['plan']=='free' and b['entitlementSources']==[]
                assert request('/api/auth/code/verify','b',{'email':'b@example.test','code':'123456'})['token']=='synthetic-b'
                request('/qa/expire',body={'owner':'a'})
                assert request('/api/onboarding/monetization/v2/status')['plan']=='free'
                assert all(row['ok'] for row in request('/qa/maps',body={}))
                print('PASS: loopback wire fixture only; native UI NOT tested',flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if worker:
            server.shutdown();worker.join(timeout=10)
        if server: server.server_close()
        fixture.tearDown()
        print('Dropped disposable schema '+fixture.schema,flush=True)


if __name__=='__main__': main()
