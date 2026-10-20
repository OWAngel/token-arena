"""Exercise a real local HTTP sparkDash fixture through the complete opt-in lifecycle."""
import argparse
import contextlib
import datetime as dt
import http.server
import io
import json
import pathlib
import plistlib
import tempfile
import threading
import unittest
from unittest.mock import patch

from arena import client
from arena.build import compile_board
from arena.core import TZ, today
from arena.sparkdash import fetch_history


class RoundtripTest(unittest.TestCase):
    def test_macos_schedule_preserves_custom_config_root_without_secret(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()), \
                patch.object(client,'CONFIG_DIR',pathlib.Path(tmp)/'token-arena'), \
                patch.object(client,'load',return_value={'enabled':True}), \
                patch.object(client.sys,'platform','darwin'),patch.object(pathlib.Path,'home',return_value=pathlib.Path(tmp)), \
                patch.object(client.shutil,'which',return_value='/usr/local/bin/gh'), \
                patch.object(client.subprocess,'run'), \
                patch.dict('os.environ',{'XDG_CONFIG_HOME':tmp,'SPARKDASH_TOKEN':'synthetic-never-in-plist'}):
            client.install_schedule(None)
            plist=plistlib.loads((pathlib.Path(tmp)/'Library/LaunchAgents/cc.sparkarena.reporter.plist').read_bytes())
            self.assertEqual(plist['EnvironmentVariables']['XDG_CONFIG_HOME'],tmp)
            self.assertNotIn('SPARKDASH_TOKEN',plist['EnvironmentVariables'])

    def test_http_connect_report_deduplicate_withdraw(self):
        day=today()-dt.timedelta(days=1)
        start=dt.datetime.combine(day,dt.time(),TZ).astimezone(dt.timezone.utc)
        fixture={"generatedAt":dt.datetime.now(TZ).timestamp()*1000,"retention":{"hours":72},
                 "hour":[{"t":(start-dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H'),"sparkId":"private-node",
                          "port":8000,"modelId":"fixture-model","promptTokens":100,"completionTokens":10,"cachedTokens":50},
                         {"t":start.strftime('%Y-%m-%dT%H'),"sparkId":"private-node","port":8000,
                          "modelId":"fixture-model","promptTokens":200,"completionTokens":20,"cachedTokens":150}]}
        requests=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path,self.headers.get('Authorization')))
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','http://example.com/');self.end_headers();return
                raw=json.dumps(fixture).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
            def log_message(self,*args): pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        stored=[]
        user={"id":42,"login":"fixture-user","type":"User"}
        def write(repo,title,body,number=None):
            if number:
                item=next(i for i in stored if i['number']==number);item.update(title=title,body=body)
            else:
                n=len(stored)+1;item={"number":n,"title":title,"body":body,"state":"open","user":user,
                    "updated_at":f'2026-10-20T01:00:{n:02}Z',"html_url":f'https://github.com/owner/repo/issues/{n}'};stored.append(item)
            return item
        def state(repo,number,value): next(i for i in stored if i['number']==number).update(state=value)
        try:
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(client,'CONFIG_DIR',pathlib.Path(tmp)),patch.object(client,'CONFIG_FILE',pathlib.Path(tmp)/'config.json'), \
                    patch.object(client,'identity',return_value=user),patch.object(client.github,'issues',side_effect=lambda _:stored), \
                    patch.object(client.github,'write_issue',side_effect=write),patch.object(client.github,'set_state',side_effect=state), \
                    patch.dict('os.environ',{'SPARKDASH_TOKEN':'synthetic-fixture-secret'}):
                url=f'http://127.0.0.1:{server.server_port}'
                client.connect(argparse.Namespace(repo='owner/repo',name='虚构测试者',url=url,consent_public=True,token_file=None))
                self.assertEqual(len(stored),1)
                args=argparse.Namespace(date=day.isoformat(),preview=True)
                client.run(args);self.assertEqual(len(stored),1)
                args.preview=False;client.run(args);client.run(args)
                self.assertEqual(len(stored),2)
                public=compile_board(stored,'owner/repo')
                self.assertEqual(public['reports'][0]['models'][0]['total_tokens'],220)
                serialized=json.dumps(public)
                for secret in ('127.0.0.1','private-node','8000','synthetic-fixture-secret'):
                    self.assertNotIn(secret,serialized)
                self.assertTrue(all(path=='/api/llm-token-totals/history' for path,auth in requests))
                self.assertTrue(all(auth=='Bearer synthetic-fixture-secret' for path,auth in requests))
                client.leave(None)
                self.assertEqual(compile_board(stored,'owner/repo')['reports'],[])
                with self.assertRaises(ValueError): client.run(args)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__': unittest.main()
