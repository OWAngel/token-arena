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

from arena import wechat_client as device
from arena.core import TZ, today
from arena.platform_service import PlatformService
from arena.wechat_service import ApiError, WechatApplication, digest
from arena.wechat_server import QuietHandler


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = PlatformService(str(pathlib.Path(self.tmp.name) / 'platform.sqlite3'))

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def join(self, nickname='合成昵称'):
        return self.service.dispatch('POST', '/v1/join', {'nickname': nickname, 'id': 'someone-else'})

    def test_no_external_identity_needed_and_names_do_not_identify_users(self):
        self.assertEqual(self.service.dispatch('GET', '/v1/board', {})['participants'], [])
        first, second = self.join(), self.join()
        self.assertNotEqual(first['user']['id'], second['user']['id'])
        self.assertNotEqual(first['user']['id'], 'someone-else')
        board = self.service.dispatch('GET', '/v1/board', {})
        self.assertEqual(len(board['participants']), 2)
        self.assertTrue(all(p['identity'] == 'web-joined' for p in board['participants']))
        self.assertNotIn(first['access_token'], json.dumps(board))
        key = first['access_token']
        stored = self.service.db.execute('SELECT hash FROM sessions WHERE user_id=?', (first['user']['id'],)).fetchone()[0]
        self.assertEqual(stored, digest(key))
        self.assertNotEqual(stored, key)
        self.assertEqual(self.service.dispatch('GET', '/v1/me', {}, key)['id'], first['user']['id'])
        with self.assertRaises(ApiError):
            self.service.dispatch('POST', '/v1/wechat/login', {'code': 'no-external-login'})

    def test_empty_name_capacity_and_device_scope(self):
        for name in ['', ' ' * 2, 'x' * 41, 'a\x00b']:
            with self.assertRaises(ValueError):
                self.join(name)
        member = self.join()
        self.service.max_participants = 1
        with self.assertRaises(ApiError) as full:
            self.join('other')
        self.assertEqual(full.exception.status, 429)
        with self.assertRaises(ApiError) as scope:
            self.service.dispatch('PUT', '/v1/reports', {}, member['access_token'])
        self.assertEqual(scope.exception.status, 401)

    def test_exit_hides_same_user_and_revokes_device(self):
        member = self.join()
        key = member['access_token']
        pair = self.service.dispatch('POST', '/v1/pair', {}, key)['pairing_code']
        token = self.service.dispatch('POST', '/v1/pair/consume', {'pairing_code': pair})['report_token']
        self.service.dispatch('DELETE', '/v1/profile', {}, key)
        self.assertEqual(self.service.dispatch('GET', '/v1/board', {})['participants'], [])
        self.assertEqual(self.service.db.execute('SELECT count(*) FROM devices').fetchone()[0], 0)
        with self.assertRaises(ApiError):
            self.service.dispatch('PUT', '/v1/reports', {}, token)

    def test_management_key_expires_and_never_becomes_report_credential(self):
        now = self.service.clock()
        self.service.clock = lambda: now
        member = self.join()
        pair = self.service.dispatch('POST', '/v1/pair', {}, member['access_token'])['pairing_code']
        device_token = self.service.dispatch('POST', '/v1/pair/consume', {'pairing_code': pair})['report_token']
        self.service.clock = lambda: now + PlatformService.SESSION_SECONDS + 1
        with self.assertRaises(ApiError) as expired:
            self.service.dispatch('GET', '/v1/me', {}, member['access_token'])
        self.assertEqual(expired.exception.status, 401)
        self.assertEqual(self.service.dispatch('GET', '/v1/board', {})['participants'], [])
        with self.assertRaises(ApiError):
            self.service.dispatch('PUT', '/v1/reports', {}, device_token)
        self.assertEqual(self.service.db.execute('SELECT count(*) FROM devices').fetchone()[0], 0)

    def test_platform_reporter_preserves_other_config_and_scheduler(self):
        root = pathlib.Path(self.tmp.name)
        sentinel = root / 'config.json'
        sentinel.write_text('{"existing":"untouched"}')
        config = root / 'platform.json'
        config.write_text('{"enabled":true}')
        config.chmod(0o600)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(device.sys, 'platform', 'darwin'), \
                patch.object(pathlib.Path, 'home', return_value=root), patch.object(device.subprocess, 'run') as process:
            device.install_schedule(None, config_path=config, module='arena.platform_client', channel='platform')
        doc = plistlib.loads((root / 'Library/LaunchAgents/cc.sparkarena.platform-reporter.plist').read_bytes())
        self.assertIn('arena.platform_client', doc['ProgramArguments'])
        self.assertEqual(doc['Label'], 'cc.sparkarena.platform-reporter')
        self.assertFalse((root / 'Library/LaunchAgents/cc.sparkarena.wechat-reporter.plist').exists())
        self.assertEqual(sentinel.read_text(), '{"existing":"untouched"}')

    def test_no_account_http_collection_pairing_reporting_and_withdrawal(self):
        day = today() - dt.timedelta(days=1)
        start = dt.datetime.combine(day, dt.time(), TZ).astimezone(dt.timezone.utc)
        fixture = {'generatedAt': dt.datetime.now(TZ).timestamp() * 1000, 'retention': {'hours': 72}, 'hour': [
            {'t': (start - dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H'), 'sparkId': 'private-source', 'port': 8000,
             'modelId': 'fixture-model', 'promptTokens': 1, 'completionTokens': 1, 'cachedTokens': 0},
            {'t': start.strftime('%Y-%m-%dT%H'), 'sparkId': 'private-source', 'port': 8000,
             'modelId': 'fixture-model', 'promptTokens': 200, 'completionTokens': 20, 'cachedTokens': 150}]}
        class Source(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(fixture).encode())
            def log_message(self, *args):
                pass
        server = make_server('127.0.0.1', 0, WechatApplication(self.service), handler_class=QuietHandler)
        source = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Source)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (server, source)]
        for thread in threads:
            thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            key = device.api_request(base, '/v1/join', 'POST', {'nickname': '合成测试者'})['access_token']
            code = device.api_request(base, '/v1/pair', 'POST', {}, key)['pairing_code']
            config = pathlib.Path(self.tmp.name) / 'platform.json'
            args = argparse.Namespace(api_base=base, url=f'http://127.0.0.1:{source.server_port}',
                                      token_file=None, token_env_file=None, consent_public=True)
            with patch.object(device.getpass, 'getpass', return_value=code), contextlib.redirect_stdout(io.StringIO()):
                device.bind(args, config_path=config, label='Spark Arena', module='arena.platform_client')
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                run = argparse.Namespace(date=day.isoformat(), preview=False)
                device.run(run, config_path=config)
                device.run(run, config_path=config)
                board = device.api_request(base, '/v1/board')
                self.assertEqual(len(board['reports']), 1)
                self.assertEqual(board['reports'][0]['models'][0]['total_tokens'], 220)
                self.assertNotIn('private-source', json.dumps(board))
                self.assertNotIn('report_token', json.dumps(board))
                device.api_request(base, '/v1/profile', 'DELETE', token=key)
                self.assertEqual(device.api_request(base, '/v1/board')['reports'], [])
                with self.assertRaises(ValueError):
                    device.run(run, config_path=config)
        finally:
            for srv in (server, source):
                srv.shutdown()
                srv.server_close()
            for thread in threads:
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
