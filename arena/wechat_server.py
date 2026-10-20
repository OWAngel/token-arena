"""Local server entrypoint; production requires an HTTPS reverse proxy and private DB."""
import os
import pathlib
from wsgiref.simple_server import WSGIRequestHandler, make_server

from .wechat_service import WechatApplication, WechatService


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def main():
    root = pathlib.Path(os.environ.get("ARENA_WECHAT_DATA", pathlib.Path.home() / ".local/share/spark-arena-wechat"))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    old_mask = os.umask(0o077)
    try:
        service = WechatService(str(root / "wechat.sqlite3"), os.environ.get("WECHAT_APPID", ""),
                                os.environ.get("WECHAT_APPSECRET", ""), os.environ.get("ARENA_IDENTITY_KEY", ""))
    finally:
        os.umask(old_mask)
    trusted = [p.strip() for p in os.environ.get("ARENA_TRUSTED_PROXIES", "").split(",") if p.strip()]
    application = WechatApplication(service, trusted_proxies=trusted)
    port = int(os.environ.get("ARENA_WECHAT_PORT", "8788"))
    print(f"WeChat service listening on loopback port {port}. Put HTTPS in front before real use.")
    with make_server("127.0.0.1", port, application, handler_class=QuietHandler) as server:
        try:
            server.serve_forever()
        finally:
            service.close()


if __name__ == "__main__":
    main()
