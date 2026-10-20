"""Separate WeChat reporter. Existing GitHub enrollment and config stay unchanged."""
import argparse
import datetime as dt
import getpass
import json
import os
import pathlib
import plistlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from .client import CONFIG_DIR, ROOT, credential, private_write
from .core import today
from .sparkdash import NoRedirect, endpoint, fetch_history, summarize

CONFIG = CONFIG_DIR / "wechat.json"


def api_base(value):
    p = urllib.parse.urlsplit(value)
    local = p.hostname in ("127.0.0.1", "localhost", "::1")
    if (p.scheme != "https" and not (p.scheme == "http" and local)) or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("Use the published HTTPS API base URL; HTTP is for loopback development only")
    return value.rstrip("/")


def api_request(base, path, method="GET", data=None, token=""):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "spark-arena-wechat/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    raw = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    request = urllib.request.Request(api_base(base) + path, data=raw, headers=headers, method=method)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=25) as r:
            body = r.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("API response is too large")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError("Invalid API response")
        return result
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        message = {401: "Device authorization expired; bind again in WeChat", 409: "This day was withdrawn; it will not be republished automatically", 429: "Rate limit; try again later"}.get(status, "WeChat service request failed")
        raise ValueError(message + f" (HTTP {status})") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError):
        raise ValueError("Cannot reach the WeChat service; check HTTPS endpoint and network") from None


def load_config():
    if not CONFIG.exists():
        raise ValueError("Not bound. Run python3 -m arena.wechat_client bind --help")
    if os.name != "nt" and CONFIG.stat().st_mode & 0o077:
        raise ValueError("WeChat device configuration must be private (chmod 600)")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def bind(args):
    if not args.consent_public:
        raise ValueError("Read the WeChat privacy notice and pass --consent-public to confirm")
    config = {"api_base": api_base(args.api_base), "url": args.url, "enabled": True}
    endpoint(args.url)
    for name in ("token_file", "token_env_file"):
        value = getattr(args, name, None)
        if value:
            config[name] = str(pathlib.Path(value).expanduser().resolve())
    summary = summarize(fetch_history(config["url"], credential(config)), today() - dt.timedelta(days=1))
    code = getpass.getpass("Paste the one-use WeChat pairing code (hidden): ").strip()
    result = api_request(config["api_base"], "/v1/pair/consume", "POST", {"pairing_code": code})
    report_token = result.get("report_token")
    if not isinstance(report_token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", report_token):
        raise ValueError("Service did not return a valid device credential")
    config["report_token"] = report_token
    private_write(CONFIG, json.dumps(config, ensure_ascii=False, indent=2))
    print("Bound to your WeChat account. Local configuration saved privately; credentials are not printed.")
    print("Yesterday's preview (not uploaded):")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Run python3 -m arena.wechat_client run when you are ready to upload.")


def run(args):
    config = load_config()
    if not config.get("enabled"):
        raise ValueError("Local WeChat reporting is paused")
    day = dt.date.fromisoformat(args.date) if args.date else today() - dt.timedelta(days=1)
    report = summarize(fetch_history(config["url"], credential(config)), day)
    if args.preview:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    # Align settlement with the existing collector's midnight flush margin.
    from .core import TZ
    now = dt.datetime.now(TZ)
    if not args.date and now.hour == 0 and now.minute < 15:
        print("Waiting until 00:15 Asia/Shanghai")
        return
    result = api_request(config["api_base"], "/v1/reports", "PUT", report, config["report_token"])
    if result.get("accepted") is not True:
        raise ValueError("Service did not acknowledge the daily report")
    print("WeChat report accepted:", result["date"], result["total_tokens"], "tokens")


def pause(_args):
    config = load_config()
    config["enabled"] = False
    private_write(CONFIG, json.dumps(config, ensure_ascii=False, indent=2))
    print("Local uploads paused. To hide the public profile, choose 退出榜单 in the WeChat mini program.")


def install_schedule(_args):
    if not load_config().get("enabled"):
        raise ValueError("Bind this device in WeChat first")
    command = [sys.executable, "-m", "arena.wechat_client", "run"]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if os.environ.get("XDG_CONFIG_HOME"):
        env["XDG_CONFIG_HOME"] = os.environ["XDG_CONFIG_HOME"]
    if sys.platform == "darwin":
        target = pathlib.Path.home() / "Library/LaunchAgents/cc.sparkarena.wechat-reporter.plist"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        doc = {"Label": "cc.sparkarena.wechat-reporter", "ProgramArguments": command,
               "WorkingDirectory": str(ROOT), "StartInterval": 3600, "RunAtLoad": True,
               "EnvironmentVariables": env, "StandardOutPath": str(CONFIG_DIR / "wechat-reporter.log"),
               "StandardErrorPath": str(CONFIG_DIR / "wechat-reporter-error.log")}
        private_write(target, plistlib.dumps(doc).decode("utf-8"))
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(target)], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True)
    elif sys.platform.startswith("linux"):
        values = [str(ROOT), *command, *env.values()]
        if any(any(c in value for c in '\n\r"%\\') for value in values):
            raise ValueError("Unsupported scheduler path; configure your scheduler manually")
        target = pathlib.Path.home() / ".config/systemd/user"
        target.mkdir(parents=True, exist_ok=True)
        service = ("[Unit]\nDescription=Spark Arena WeChat reporter\n[Service]\nType=oneshot\n"
                   f'WorkingDirectory="{ROOT}"\n' + ''.join(f'Environment="{k}={v}"\n' for k,v in env.items()) +
                   'ExecStart=' + ' '.join('"'+v+'"' for v in command) + '\n')
        (target / "spark-arena-wechat.service").write_text(service)
        (target / "spark-arena-wechat.timer").write_text("[Unit]\nDescription=Check yesterday's WeChat report hourly\n"
            "[Timer]\nOnBootSec=2min\nOnUnitActiveSec=1h\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "spark-arena-wechat.timer"], check=True)
    else:
        raise ValueError("Use Windows Task Scheduler to run python -m arena.wechat_client run hourly")
    print("Independent WeChat hourly reporter installed. The existing GitHub reporter was not changed.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(required=True)
    b = sub.add_parser("bind")
    b.add_argument("--api-base", required=True)
    b.add_argument("--url", required=True)
    auth = b.add_mutually_exclusive_group()
    auth.add_argument("--token-file")
    auth.add_argument("--token-env-file")
    b.add_argument("--consent-public", action="store_true")
    b.set_defaults(func=bind)
    r = sub.add_parser("run")
    r.add_argument("--date")
    r.add_argument("--preview", action="store_true")
    r.set_defaults(func=run)
    sub.add_parser("pause").set_defaults(func=pause)
    sub.add_parser("install-schedule").set_defaults(func=install_schedule)
    args = p.parse_args()
    try:
        args.func(args)
    except ValueError as error:
        print("Error:", error, file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.CalledProcessError):
        print("Local file or scheduler operation failed. Check permissions and the selected user session.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
