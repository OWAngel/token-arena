"""Account-free web enrollment. Private management keys identify participants."""
import secrets
import time

from .core import text
from .wechat_service import ApiError, UsageService, digest


class PlatformService(UsageService):
    SESSION_SECONDS = 365 * 24 * 3600

    def __init__(self, db_path, clock=time.time, max_participants=10000):
        super().__init__(db_path, clock)
        self.max_participants = max_participants

    def dispatch(self, method, path, body, token=""):
        # If management access expires, stop devices and hide records together.
        # No participant can be left publishing after losing their control key.
        with self.transaction():
            self.db.execute("UPDATE users SET active=0 WHERE active=1 AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.user_id=users.id AND s.expires>?)", (self.clock(),))
            self.db.execute("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE active=0)")
            self.db.execute("DELETE FROM pairs WHERE user_id IN (SELECT id FROM users WHERE active=0)")
            self.db.execute("UPDATE reports SET withdrawn=1 WHERE withdrawn=0 AND user_id IN (SELECT id FROM users WHERE active=0)")
        if path == "/health" and method == "GET":
            return {"ok": True, "service": "spark-arena-platform", "version": 1}
        if path == "/v1/join" and method == "POST":
            nickname = text(body.get("nickname"), 40)
            uid, key = "web_" + secrets.token_hex(16), secrets.token_urlsafe(32)
            with self.transaction():
                if self.db.execute("SELECT count(*) FROM users").fetchone()[0] >= self.max_participants:
                    raise ApiError(429, "当前报名名额已满，请稍后再试")
                self.db.execute("DELETE FROM sessions WHERE expires<=?", (self.clock(),))
                self.db.execute("INSERT INTO users VALUES(?,?,1)", (uid, nickname))
                self.db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(key), uid, self.clock() + self.SESSION_SECONDS))
                return {"access_token": key, "expires_in": self.SESSION_SECONDS, "user": self._me(uid)}
        # Web mode has no WeChat code exchange and never accepts supplied IDs.
        if path == "/v1/wechat/login":
            raise ApiError(404, "接口不存在")
        return super().dispatch(method, path, body, token)
