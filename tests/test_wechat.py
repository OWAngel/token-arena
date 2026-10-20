import concurrent.futures
import datetime as dt
import io
import json
import pathlib
import tempfile
import unittest

from arena.core import today
from arena.wechat_service import ApiError, WechatApplication, WechatService


def report(value=100):
    return {"version":1,"kind":"usage","consent_public":True,
            "date":(today()-dt.timedelta(days=1)).isoformat(),"timezone":"Asia/Shanghai",
            "coverage":"recorded-window","models":[{"model":"synthetic-model","input_tokens":value,
                "output_tokens":10,"cached_input_tokens":80}],"source_url":"private://do-not-publish",
            "openid":"client-cannot-choose-user"}


class WechatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.clock=[dt.datetime.now().timestamp()]
        self.path=str(pathlib.Path(self.tmp.name)/'test.sqlite3')
        self.service=WechatService(self.path,'wx0123456789abcdef','synthetic-secret-only',
            'synthetic-stable-identity-key-for-tests',exchange=lambda app,secret,code:'official-openid-'+code,
            clock=lambda:self.clock[0])

    def tearDown(self):
        self.service.close();self.tmp.cleanup()

    def login(self,code='alice'):
        return self.service.dispatch('POST','/v1/wechat/login',{'code':code,'openid':'spoofed','id':'other-user'})

    def enroll(self,session,name='虚构昵称'):
        return self.service.dispatch('PUT','/v1/profile',{'nickname':name,'consent_public':True},session)

    def device(self,session):
        code=self.service.dispatch('POST','/v1/pair',{},session)['pairing_code']
        return self.service.dispatch('POST','/v1/pair/consume',{'pairing_code':code})['report_token']

    def test_login_is_not_enrollment_and_does_not_publish_openid(self):
        a=self.login();b=self.login()
        self.assertEqual(a['user']['id'],b['user']['id'])
        self.assertNotEqual(a['access_token'],b['access_token'])
        self.assertEqual(self.service.dispatch('GET','/v1/board',{})['participants'],[])
        self.assertNotIn('official-openid',json.dumps(a))
        self.assertNotIn('official-openid',self.service.db.execute('SELECT id FROM users').fetchone()[0])

    def test_enrollment_requires_consent_and_pairing_requires_enrollment(self):
        token=self.login()['access_token']
        with self.assertRaises(ApiError):self.service.dispatch('POST','/v1/pair',{},token)
        with self.assertRaises(ApiError):self.service.dispatch('PUT','/v1/profile',{'nickname':'n'},token)

    def test_same_nickname_different_identity(self):
        a,b=self.login('alice'),self.login('bob')
        self.enroll(a['access_token']);self.enroll(b['access_token'])
        self.assertEqual(len(self.service.dispatch('GET','/v1/board',{})['participants']),2)
        self.assertNotEqual(a['user']['id'],b['user']['id'])

    def test_pair_code_single_use_and_device_tokens_are_hashed(self):
        session=self.login()['access_token'];self.enroll(session)
        code=self.service.dispatch('POST','/v1/pair',{},session)['pairing_code']
        result=self.service.dispatch('POST','/v1/pair/consume',{'pairing_code':code})
        with self.assertRaises(ApiError):self.service.dispatch('POST','/v1/pair/consume',{'pairing_code':code})
        self.assertNotEqual(self.service.db.execute('SELECT hash FROM devices').fetchone()[0],result['report_token'])
        self.assertNotEqual(self.service.db.execute('SELECT hash FROM sessions LIMIT 1').fetchone()[0],session)

    def test_pair_ttl_and_regeneration_invalidate_old_code(self):
        session=self.login()['access_token'];self.enroll(session)
        first=self.service.dispatch('POST','/v1/pair',{},session)['pairing_code']
        second=self.service.dispatch('POST','/v1/pair',{},session)['pairing_code']
        with self.assertRaises(ApiError):self.service.dispatch('POST','/v1/pair/consume',{'pairing_code':first})
        self.clock[0]+=601
        with self.assertRaises(ApiError):self.service.dispatch('POST','/v1/pair/consume',{'pairing_code':second})

    def test_concurrent_pair_claims_have_exactly_one_success(self):
        session=self.login()['access_token'];self.enroll(session)
        code=self.service.dispatch('POST','/v1/pair',{},session)['pairing_code']
        def claim(_):
            try:self.service.dispatch('POST','/v1/pair/consume',{'pairing_code':code});return True
            except ApiError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(claim,range(4))),1)

    def test_session_and_device_scopes_are_not_interchangeable(self):
        session=self.login()['access_token'];self.enroll(session);device=self.device(session)
        with self.assertRaises(ApiError):self.service.dispatch('PUT','/v1/reports',report(),session)
        with self.assertRaises(ApiError):self.service.dispatch('GET','/v1/me',{},device)
        with self.assertRaises(ApiError):self.service.dispatch('DELETE','/v1/profile',{},device)

    def test_report_upsert_allowlist_cache_and_ownership(self):
        alice,bob=self.login('alice')['access_token'],self.login('bob')['access_token']
        self.enroll(alice,'Alice');self.enroll(bob,'Bob')
        device=self.device(alice)
        self.service.dispatch('PUT','/v1/reports',report(),device)
        self.service.dispatch('PUT','/v1/reports',report(200),device)
        board=self.service.dispatch('GET','/v1/board',{})
        self.assertEqual(len(board['reports']),1)
        r=board['reports'][0]
        self.assertEqual(r['models'][0]['total_tokens'],210)
        self.assertEqual(r['wechat_name'],'Alice')
        self.assertEqual(r['id'],self.service.dispatch('GET','/v1/me',{},alice)['id'])
        for private in ['official-openid','client-cannot-choose-user','private://','access_token','report_token']:
            self.assertNotIn(private,json.dumps(board))

    def test_revoke_and_exit_hide_reports_and_require_new_device(self):
        session=self.login()['access_token'];self.enroll(session);device=self.device(session)
        self.service.dispatch('PUT','/v1/reports',report(),device)
        self.service.dispatch('DELETE','/v1/devices',{},session)
        with self.assertRaises(ApiError):self.service.dispatch('PUT','/v1/reports',report(),device)
        device=self.device(session)
        self.service.dispatch('DELETE','/v1/profile',{},session)
        self.assertEqual(self.service.dispatch('GET','/v1/board',{})['reports'],[])
        with self.assertRaises(ApiError):self.service.dispatch('PUT','/v1/reports',report(),device)
        self.enroll(session);new_device=self.device(session)
        self.assertEqual(self.service.dispatch('GET','/v1/board',{})['reports'],[])
        with self.assertRaises(ApiError):self.service.dispatch('PUT','/v1/reports',report(),new_device)

    def test_day_withdrawal_does_not_hide_other_user_or_auto_reopen(self):
        session=self.login()['access_token'];self.enroll(session);device=self.device(session)
        self.service.dispatch('PUT','/v1/reports',report(),device)
        self.service.dispatch('DELETE','/v1/reports/'+report()['date'],{},session)
        with self.assertRaises(ApiError) as error:self.service.dispatch('PUT','/v1/reports',report(),device)
        self.assertEqual(error.exception.status,409)

    def test_withdrawal_before_first_upload_leaves_a_tombstone(self):
        session=self.login()['access_token'];self.enroll(session);device=self.device(session)
        self.service.dispatch('DELETE','/v1/reports/'+report()['date'],{},session)
        with self.assertRaises(ApiError) as error:self.service.dispatch('PUT','/v1/reports',report(),device)
        self.assertEqual(error.exception.status,409)
        with self.assertRaises(ValueError):self.service.dispatch('DELETE','/v1/reports/'+today().isoformat(),{},session)

    def test_trusted_proxy_overwrites_client_ip_and_untrusted_headers_are_ignored(self):
        app=WechatApplication(self.service,trusted_proxies=['127.0.0.1'])
        def call(remote,real):
            result=[]
            b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':'/health','REMOTE_ADDR':remote,
                'HTTP_X_REAL_IP':real,'CONTENT_LENGTH':'0'},lambda status,h:result.append(status)))
            return result[0]
        for _ in range(120):self.assertTrue(call('127.0.0.1','192.0.2.1').startswith('200'))
        self.assertTrue(call('127.0.0.1','192.0.2.1').startswith('429'))
        self.assertTrue(call('127.0.0.1','192.0.2.2').startswith('200'))
        self.assertTrue(call('127.0.0.1','192.0.2.1,192.0.2.2').startswith('400'))
        for i in range(120):self.assertTrue(call('untrusted',f'192.0.2.{i}').startswith('200'))
        self.assertTrue(call('untrusted','192.0.2.200').startswith('429'))

    def test_persisted_device_and_profile_survive_restart(self):
        session=self.login()['access_token'];self.enroll(session);device=self.device(session)
        self.service.dispatch('PUT','/v1/reports',report(),device)
        self.service.close()
        self.service=WechatService(self.path,'wx0123456789abcdef','synthetic-secret-only',
            'synthetic-stable-identity-key-for-tests',exchange=lambda a,s,c:'official-openid-'+c,
            clock=lambda:self.clock[0])
        self.service.dispatch('PUT','/v1/reports',report(),device)
        self.assertEqual(len(self.service.dispatch('GET','/v1/board',{})['reports']),1)

    def test_session_expiration_and_logout(self):
        session=self.login()['access_token']
        self.service.dispatch('DELETE','/v1/session',{},session)
        with self.assertRaises(ApiError):self.service.dispatch('GET','/v1/me',{},session)
        session=self.login()['access_token'];self.clock[0]+=86401
        with self.assertRaises(ApiError):self.service.dispatch('GET','/v1/me',{},session)

    def test_wsgi_boundaries_and_no_sensitive_errors(self):
        app=WechatApplication(self.service)
        def call(body=b'{}',**values):
            env={'REQUEST_METHOD':'POST','PATH_INFO':'/v1/wechat/login','CONTENT_LENGTH':str(len(body)),
                 'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(body),'REMOTE_ADDR':'fixture',**values}
            result=[];raw=b''.join(app(env,lambda status,headers:result.append((status,headers))))
            return result[0][0],json.loads(raw)
        self.assertTrue(call(b'[]')[0].startswith('400'))
        self.assertTrue(call(b'{}',CONTENT_LENGTH='999999')[0].startswith('413'))
        self.assertTrue(call(QUERY_STRING='token=never-accepted')[0].startswith('400'))
        self.assertTrue(call(CONTENT_TYPE='text/plain')[0].startswith('415'))
        deep=b'['*20000+b'0'+b']'*20000
        self.assertTrue(call(deep)[0].startswith('400'))
        self.service.exchange=lambda *args:(_ for _ in ()).throw(RuntimeError('synthetic-secret-only'))
        status,body=call(b'{"code":"test"}')
        self.assertTrue(status.startswith('500'));self.assertNotIn('synthetic-secret-only',json.dumps(body))


if __name__=='__main__':unittest.main()
