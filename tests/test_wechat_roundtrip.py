import argparse
import contextlib
import datetime as dt
import http.server
import io
import json
import os
import pathlib
import plistlib
import tempfile
import threading
import unittest
from unittest.mock import patch
from wsgiref.simple_server import make_server

from arena import wechat_client as client
from arena.core import TZ, today
from arena.wechat_server import QuietHandler
from arena.wechat_service import WechatApplication, WechatService


class WechatRoundtripTest(unittest.TestCase):
    def test_local_http_source_to_wechat_binding_report_and_revocation(self):
        day=today()-dt.timedelta(days=1)
        start=dt.datetime.combine(day,dt.time(),TZ).astimezone(dt.timezone.utc)
        fixture={'generatedAt':dt.datetime.now(TZ).timestamp()*1000,'retention':{'hours':72},'hour':[
            {'t':(start-dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H'),'sparkId':'private-node','port':8000,
             'modelId':'fixture-model','promptTokens':100,'completionTokens':20,'cachedTokens':80},
            {'t':start.strftime('%Y-%m-%dT%H'),'sparkId':'private-node','port':8000,
             'modelId':'fixture-model','promptTokens':200,'completionTokens':20,'cachedTokens':150}]}
        class Source(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(fixture).encode())
            def log_message(self,*args):pass
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=pathlib.Path(tmp)
            service=WechatService(str(root/'test.sqlite3'),'wx0123456789abcdef','synthetic-secret-value',
                'synthetic-stable-identity-key-for-test',exchange=lambda a,s,c:'official-fixture-openid')
            server=make_server('127.0.0.1',0,WechatApplication(service),handler_class=QuietHandler)
            source=http.server.ThreadingHTTPServer(('127.0.0.1',0),Source)
            threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (server,source)]
            for thread in threads:thread.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                session=client.api_request(base,'/v1/wechat/login','POST',{'code':'fixture-code'})['access_token']
                client.api_request(base,'/v1/profile','PUT',{'nickname':'合成测试者','consent_public':True},session)
                code=client.api_request(base,'/v1/pair','POST',{},session)['pairing_code']
                sentinel=root/'github-config.json';sentinel.write_text('{"unchanged":true}')
                config=root/'wechat.json'
                with patch.object(client,'CONFIG',config),patch.object(client,'credential',return_value=''), \
                     patch.object(client.getpass,'getpass',return_value=code):
                    client.bind(argparse.Namespace(api_base=base,url=f'http://127.0.0.1:{source.server_port}',
                        token_file=None,token_env_file=None,consent_public=True))
                    self.assertEqual(sentinel.read_text(),'{"unchanged":true}')
                    self.assertEqual(config.stat().st_mode&0o777,0o600)
                    args=argparse.Namespace(date=day.isoformat(),preview=True)
                    client.run(args);self.assertEqual(client.api_request(base,'/v1/board')['reports'],[])
                    args.preview=False;client.run(args);client.run(args)
                    board=client.api_request(base,'/v1/board')
                    self.assertEqual(len(board['reports']),1)
                    self.assertEqual(board['reports'][0]['models'][0]['total_tokens'],220)
                    for secret in ['private-node','official-fixture-openid','report_token','synthetic-secret-value']:
                        self.assertNotIn(secret,json.dumps(board))
                    client.api_request(base,'/v1/profile','DELETE',token=session)
                    self.assertEqual(client.api_request(base,'/v1/board')['reports'],[])
                    with self.assertRaises(ValueError):client.run(args)
                    client.pause(None)
                    with self.assertRaises(ValueError):client.run(args)
                    self.assertEqual(sentinel.read_text(),'{"unchanged":true}')
            finally:
                server.shutdown();source.shutdown();server.server_close();source.server_close()
                for thread in threads:thread.join(timeout=2)
                service.close()

    def test_wechat_scheduler_uses_a_separate_agent_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()), \
                patch.object(client,'CONFIG_DIR',pathlib.Path(tmp)/'token-arena'), \
                patch.object(client,'load_config',return_value={'enabled':True}), \
                patch.object(client.sys,'platform','darwin'),patch.object(pathlib.Path,'home',return_value=pathlib.Path(tmp)), \
                patch.object(client.subprocess,'run') as run,patch.dict(os.environ,{'XDG_CONFIG_HOME':tmp}):
            client.install_schedule(None)
            folder=pathlib.Path(tmp)/'Library/LaunchAgents'
            self.assertFalse((folder/'cc.sparkarena.reporter.plist').exists())
            doc=plistlib.loads((folder/'cc.sparkarena.wechat-reporter.plist').read_bytes())
            self.assertIn('arena.wechat_client',doc['ProgramArguments'])
            self.assertEqual(doc['StartInterval'],3600)
            self.assertEqual(doc['EnvironmentVariables']['XDG_CONFIG_HOME'],tmp)
            self.assertNotIn('SPARKDASH_TOKEN',doc['EnvironmentVariables'])
            self.assertEqual(run.call_args.args[0][1],'bootstrap')


if __name__=='__main__':unittest.main()
