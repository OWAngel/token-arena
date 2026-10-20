"""Independent web API, with no GitHub or WeChat credentials."""
import os
import pathlib

from .platform_service import PlatformService
from .wechat_service import WechatApplication


def create_app():
    root = pathlib.Path(os.environ.get("ARENA_PLATFORM_DATA", pathlib.Path.home() / ".local/share/spark-arena-platform"))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    old_mask = os.umask(0o077)
    try:
        service = PlatformService(str(root / "platform.sqlite3"))
    finally:
        os.umask(old_mask)
    trusted = [p.strip() for p in os.environ.get("ARENA_TRUSTED_PROXIES", "").split(",") if p.strip()]
    return WechatApplication(service, trusted_proxies=trusted)


def main():
    from wsgiref.simple_server import make_server
    from .wechat_server import QuietHandler
    application = create_app()
    port = int(os.environ.get("ARENA_PLATFORM_PORT", "8789"))
    with make_server("127.0.0.1", port, application, handler_class=QuietHandler) as server:
        try:
            server.serve_forever()
        finally:
            application.service.close()


if __name__ == "__main__":
    main()
