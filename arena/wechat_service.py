"""Isolated WeChat identity/report service. It does not modify the GitHub board.

Run behind HTTPS with a persistent private database. Identity is obtained only
from the server-side WeChat code exchange; OpenID and credentials stay private.
"""
import datetime as dt
import contextlib
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .core import text, validate
from .sparkdash import NoRedirect


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def exchange_code(appid, secret, code):
    """Call the fixed official host. Never return session_key or echo errors/URLs."""
    query = urllib.parse.urlencode({"appid": appid, "secret": secret,
                                   "js_code": code, "grant_type": "authorization_code"})
    request = urllib.request.Request("https://api.weixin.qq.com/sns/jscode2session?" + query)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=15) as r:
            raw = r.read(16385)
        if len(raw) > 16384:
            raise ValueError("response limit")
        data = json.loads(raw)
        openid = data.get("openid")
        if data.get("errcode") or not isinstance(openid, str) or not 8 <= len(openid) <= 128:
            raise ApiError(401, "微信登录凭证无效，请重新登录")
        return openid
    except ApiError:
        raise
    except (OSError, ValueError, AttributeError):
        raise ApiError(502, "微信登录服务暂时不可用，请稍后重试") from None


class WechatService:
    SESSION_SECONDS = 24 * 3600
    PAIR_SECONDS = 600

    def __init__(self, db_path, appid, appsecret, identity_key, exchange=None, clock=time.time):
        if not re.fullmatch(r"wx[0-9a-f]{16}", appid) or len(appsecret) < 16 or len(identity_key) < 32:
            raise ValueError("Set the new AppID, server-only AppSecret and a stable 32+ character identity key")
        self.appid, self.secret, self.identity_key = appid, appsecret, identity_key
        self.exchange, self.clock = exchange or exchange_code, clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, nickname TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pairs (
                hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                user_id TEXT NOT NULL REFERENCES users(id), day TEXT NOT NULL,
                body TEXT NOT NULL, withdrawn INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL,
                PRIMARY KEY(user_id,day)
            );
        """)

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def transaction(self):
        # Serializes consent/revocation against uploads across both threads and
        # independent worker processes sharing this SQLite database.
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            else:
                self.db.execute("COMMIT")

    def user_id(self, openid):
        return "wx_" + hmac.new(self.identity_key.encode(), (self.appid + ":" + openid).encode(), hashlib.sha256).hexdigest()[:32]

    def _authorize(self, token, scope="session"):
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise ApiError(401, "请重新登录或绑定设备")
        if scope == "session":
            row = self.db.execute("SELECT user_id FROM sessions WHERE hash=? AND expires>?", (digest(token), self.clock())).fetchone()
        else:
            row = self.db.execute("SELECT d.user_id FROM devices d JOIN users u ON u.id=d.user_id WHERE d.hash=? AND u.active=1", (digest(token),)).fetchone()
        if not row:
            raise ApiError(401, "登录或设备授权已过期，请重新绑定")
        return row["user_id"]

    def _me(self, uid):
        row = self.db.execute("SELECT nickname,active FROM users WHERE id=?", (uid,)).fetchone()
        devices = self.db.execute("SELECT count(*) FROM devices WHERE user_id=?", (uid,)).fetchone()[0]
        return {"id": uid, "nickname": row["nickname"], "consent_public": bool(row["active"]), "device_count": devices}

    def dispatch(self, method, path, body, token=""):
        if path == "/v1/wechat/login" and method == "POST":
            code = text(body.get("code"), 512)
            # Neither body.openid nor client-supplied user IDs are ever trusted.
            openid = self.exchange(self.appid, self.secret, code)
            uid, session = self.user_id(openid), secrets.token_urlsafe(32)
            with self.transaction():
                self.db.execute("DELETE FROM sessions WHERE expires<=?", (self.clock(),))
                self.db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
                self.db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(session), uid, self.clock() + self.SESSION_SECONDS))
                return {"access_token": session, "expires_in": self.SESSION_SECONDS, "user": self._me(uid)}
        with self.transaction():
            if path == "/health" and method == "GET":
                return {"ok": True, "service": "spark-arena-wechat", "version": 1}
            if path == "/v1/board" and method == "GET":
                return self._board()
            if path == "/v1/pair/consume" and method == "POST":
                return self._consume(body)
            if path == "/v1/reports" and method == "PUT":
                return self._report(self._authorize(token, "device"), body)
            uid = self._authorize(token)
            if path == "/v1/me" and method == "GET":
                return self._me(uid)
            if path == "/v1/session" and method == "DELETE":
                self.db.execute("DELETE FROM sessions WHERE hash=?", (digest(token),))
                return {"logged_out": True}
            if path == "/v1/profile" and method == "PUT":
                if body.get("consent_public") is not True:
                    raise ApiError(400, "请明确同意公开昵称和模型用量")
                nickname = text(body.get("nickname"), 40)
                self.db.execute("UPDATE users SET nickname=?,active=1 WHERE id=?", (nickname, uid))
                return self._me(uid)
            if path == "/v1/pair" and method == "POST":
                if not self._me(uid)["consent_public"]:
                    raise ApiError(403, "请先自主报名")
                code = secrets.token_urlsafe(24)
                self.db.execute("DELETE FROM pairs WHERE user_id=? OR expires<=?", (uid, self.clock()))
                self.db.execute("INSERT INTO pairs VALUES(?,?,?)", (digest(code), uid, self.clock() + self.PAIR_SECONDS))
                return {"pairing_code": code, "expires_in": self.PAIR_SECONDS}
            if path == "/v1/devices" and method == "DELETE":
                self.db.execute("DELETE FROM devices WHERE user_id=?", (uid,))
                self.db.execute("DELETE FROM pairs WHERE user_id=?", (uid,))
                return self._me(uid)
            if path == "/v1/profile" and method == "DELETE":
                self.db.execute("UPDATE users SET active=0 WHERE id=?", (uid,))
                self.db.execute("DELETE FROM devices WHERE user_id=?", (uid,))
                self.db.execute("DELETE FROM pairs WHERE user_id=?", (uid,))
                self.db.execute("UPDATE reports SET withdrawn=1 WHERE user_id=?", (uid,))
                return self._me(uid)
            if path.startswith("/v1/reports/") and method == "DELETE":
                day = path.removeprefix("/v1/reports/")
                validate({"version":1,"kind":"usage","consent_public":True,"date":day,
                          "timezone":"Asia/Shanghai","coverage":"partial","models":[]})
                self.db.execute("INSERT INTO reports(user_id,day,body,withdrawn,updated) VALUES(?,?,'{}',1,?) ON CONFLICT(user_id,day) DO UPDATE SET withdrawn=1,updated=excluded.updated", (uid, day, self.clock()))
                return {"withdrawn": True, "date": day}
            raise ApiError(404, "接口不存在")

    def _consume(self, body):
        code = body.get("pairing_code")
        if not isinstance(code, str) or not 32 <= len(code) <= 128:
            raise ApiError(401, "绑定码无效或已过期")
        pair = self.db.execute("SELECT p.user_id FROM pairs p JOIN users u ON u.id=p.user_id WHERE p.hash=? AND p.expires>? AND u.active=1", (digest(code), self.clock())).fetchone()
        if not pair:
            raise ApiError(401, "绑定码无效、已使用或已过期")
        uid, report_token = pair["user_id"], secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM pairs WHERE hash=?", (digest(code),))
        self.db.execute("INSERT INTO devices VALUES(?,?,?)", (digest(report_token), uid, self.clock()))
        return {"report_token": report_token, "user": self._me(uid)}

    def _report(self, uid, body):
        report = validate(body)
        if report["kind"] != "usage":
            raise ApiError(400, "请上传每日用量汇总")
        old = self.db.execute("SELECT withdrawn FROM reports WHERE user_id=? AND day=?", (uid, report["date"])).fetchone()
        if old and old["withdrawn"]:
            raise ApiError(409, "该日报已被本人撤回，不会自动重新发布")
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.db.execute("INSERT INTO reports(user_id,day,body,updated) VALUES(?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET body=excluded.body,updated=excluded.updated", (uid, report["date"], serialized, self.clock()))
        return {"accepted": True, "date": report["date"], "total_tokens": sum(m["total_tokens"] for m in report["models"])}

    def _board(self):
        participants = [{"id": r["id"], "wechat_name": r["nickname"], "identity": "wechat-login"}
                        for r in self.db.execute("SELECT id,nickname FROM users WHERE active=1 ORDER BY id")]
        reports = []
        for r in self.db.execute("SELECT r.*,u.nickname FROM reports r JOIN users u ON u.id=r.user_id WHERE u.active=1 AND r.withdrawn=0 ORDER BY r.day,r.user_id"):
            report = json.loads(r["body"])
            reports.append({**report, "id": r["user_id"], "wechat_name": r["nickname"], "identity": "wechat-login"})
        return {"version": 1, "timezone": "Asia/Shanghai", "generated_at": dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).isoformat(), "participants": participants, "reports": reports}


class WechatApplication:
    """Small WSGI boundary. No CORS credentials, token URLs, proxy trust, or raw logs."""
    def __init__(self, service, trusted_proxies=()):
        self.service = service
        self.lock = threading.Lock()
        self.rates = {}
        self.trusted_proxies = {str(ipaddress.ip_address(p)) for p in trusted_proxies}

    def __call__(self, environ, start_response):
        try:
            method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
            if environ.get("QUERY_STRING"):
                raise ApiError(400, "请勿在URL中携带凭据或参数")
            remote, now = environ.get("REMOTE_ADDR", ""), self.service.clock()
            if remote in self.trusted_proxies:
                try:
                    remote = str(ipaddress.ip_address(environ.get("HTTP_X_REAL_IP", "")))
                except ValueError:
                    raise ApiError(400, "受信代理须覆盖提供有效的客户端IP") from None
            with self.lock:
                # Reverse proxies must enforce an additional per-client rate limit.
                self.rates = {k: v for k, v in self.rates.items() if v[0] > now - 60}
                since, count = self.rates.get(remote, (now, 0))
                if count >= 120 or len(self.rates) >= 10000 and remote not in self.rates:
                    raise ApiError(429, "请求过于频繁，请稍后重试")
                self.rates[remote] = (since, count + 1)
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length < 0 or length > 65536:
                raise ApiError(413, "请求内容过大")
            body = {}
            if method in ("POST", "PUT"):
                if environ.get("CONTENT_TYPE", "").split(";")[0] != "application/json":
                    raise ApiError(415, "请使用JSON请求")
                body = json.loads(environ["wsgi.input"].read(length))
                if not isinstance(body, dict):
                    raise ValueError("object required")
            authorization = environ.get("HTTP_AUTHORIZATION", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            result = self.service.dispatch(method, path, body, token)
            status = 200
        except ApiError as exc:
            status, result = exc.status, {"error": exc.message}
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
            status, result = 400, {"error": "请求格式无效"}
        except Exception:
            status, result = 500, {"error": "服务暂时不可用，请稍后重试"}
        raw = json.dumps(result, ensure_ascii=False).encode()
        reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 409: "Conflict", 413: "Content Too Large", 415: "Unsupported Media Type", 429: "Too Many Requests", 500: "Internal Server Error", 502: "Bad Gateway"}[status]
        start_response(f"{status} {reason}", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(raw))), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")])
        return [raw]
