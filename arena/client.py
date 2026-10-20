"""Participant-side reporter. All sparkDash networking happens on this computer."""
import argparse
import datetime as dt
import getpass
import json
import os
import pathlib
import plistlib
import shlex
import shutil
import subprocess
import sys

from . import github
from .core import TZ, issue_body, parse_body, text, today
from .sparkdash import endpoint, fetch_history, summarize

CONFIG_DIR = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config") / "token-arena"
CONFIG_FILE = CONFIG_DIR / "config.json"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load():
    if not CONFIG_FILE.exists():
        raise ValueError("Not connected. Run python3 -m arena.client connect --help")
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def credential(config):
    value = os.environ.get("SPARKDASH_TOKEN", "").strip()
    if value:
        return value
    if config.get("token_env_file"):
        path = pathlib.Path(config["token_env_file"]).expanduser()
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError("Credential environment file must be private: chmod 600 <env-file>")
        found = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, raw = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            if separator and key in ("SPARKDASH_TOKEN", "DASHBOARD_TOKEN"):
                try:
                    values = shlex.split(raw, comments=True)
                except ValueError:
                    raise ValueError("Malformed credential assignment in local environment file") from None
                if len(values) > 1:
                    raise ValueError("Quote credential values containing whitespace")
                found[key] = values[0] if values else ""
        return found.get("SPARKDASH_TOKEN") or found.get("DASHBOARD_TOKEN") or ""
    path = pathlib.Path(config.get("token_file", str(CONFIG_DIR / "sparkdash.token"))).expanduser()
    if path.exists():
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError("Token file must be private: chmod 600 <token-file>")
        return path.read_text(encoding="utf-8").strip()
    return ""


def owned(all_issues, uid, kind, day=None):
    matches = []
    for issue in all_issues:
        if str(issue.get("user", {}).get("id")) != str(uid):
            continue
        try:
            body = parse_body(issue.get("body"))
        except (ValueError, TypeError):
            continue
        if body["kind"] == kind and (day is None or body.get("date") == day):
            matches.append(issue)
    return sorted(matches, key=lambda x: (x["updated_at"], x["number"]))


def identity():
    return github.gh(["api", "user"])


def connect(args):
    if not args.consent_public:
        raise ValueError("Read PRIVACY.md and pass --consent-public to opt in")
    config = {"repo": github.repo_name(args.repo), "wechat_name": text(args.name, 40),
              "url": args.url, "enabled": True}
    endpoint(args.url)
    if args.token_file:
        config["token_file"] = str(pathlib.Path(args.token_file).expanduser().resolve())
    if args.token_env_file:
        config["token_env_file"] = str(pathlib.Path(args.token_env_file).expanduser().resolve())
    # Validate connectivity and the actual wire contract before opening a public enrollment.
    history = fetch_history(config["url"], credential(config))
    preview = summarize(history, today() - dt.timedelta(days=1))
    user = identity()
    config["github_id"] = user["id"]
    data = github.issues(config["repo"])
    previous = owned(data, user["id"], "participant")
    payload = {"version": 1, "kind": "participant", "consent_public": True,
               "wechat_name": config["wechat_name"]}
    current = previous[-1] if previous and previous[-1]["state"] == "open" else None
    result = github.write_issue(config["repo"], "[participant] " + user["login"], issue_body(payload),
                                current["number"] if current else None)
    private_write(CONFIG_FILE, json.dumps(config, ensure_ascii=False, indent=2))
    print("Connected. Public enrollment:", result["html_url"])
    print("Yesterday's preview (not yet uploaded):")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    print("Run 'python3 -m arena.client run', then 'python3 -m arena.client install-schedule'.")


def run(args):
    config = load()
    if not config.get("enabled"):
        raise ValueError("Participation is disabled")
    day = dt.date.fromisoformat(args.date) if args.date else today() - dt.timedelta(days=1)
    report = summarize(fetch_history(config["url"], credential(config)), day)
    if args.preview:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    # Wait for the upstream's 30-second flush after midnight.
    now = dt.datetime.now(TZ)
    if not args.date and now.hour == 0 and now.minute < 15:
        print("Waiting until 00:15 Asia/Shanghai for previous-day settlement")
        return
    user = identity()
    if user["id"] != config["github_id"]:
        raise ValueError("GitHub account changed; reconnect with explicit consent")
    all_issues = github.issues(config["repo"])
    enrollments = owned(all_issues, user["id"], "participant")
    if not enrollments or enrollments[-1]["state"] != "open":
        raise ValueError("Enrollment closed or missing. Upload paused; reconnect explicitly to rejoin")
    prior = owned(all_issues, user["id"], "usage", day.isoformat())
    if prior and prior[-1]["state"] == "closed":
        print("This day's report was withdrawn; it will not be reopened automatically")
        return
    body = issue_body(report)
    if prior and prior[-1]["body"] == body:
        print("Already uploaded; unchanged")
        return
    result = github.write_issue(config["repo"], f"[usage] {user['login']} {day}", body,
                                prior[-1]["number"] if prior else None)
    print("Uploaded:", result["html_url"])


def leave(_args):
    config = load()
    config["enabled"] = False
    private_write(CONFIG_FILE, json.dumps(config, ensure_ascii=False, indent=2))
    user = identity()
    if user["id"] != config["github_id"]:
        raise ValueError("Local uploads disabled. Switch back to the original GitHub account to close enrollment")
    for issue in owned(github.issues(config["repo"]), user["id"], "participant"):
        if issue["state"] == "open":
            github.set_state(config["repo"], issue["number"], "closed")
    print("Uploads disabled; enrollment closed. Board removal follows the next successful rebuild.")
    print("Public GitHub issue history remains accessible. See PRIVACY.md.")


def save_token(_args):
    token = getpass.getpass("sparkDash bearer token (stored only on this computer): ").strip()
    if not token or "\n" in token or "\r" in token:
        raise ValueError("Expected a single non-empty token")
    private_write(CONFIG_DIR / "sparkdash.token", token + "\n")
    print("Saved privately on this computer. The token is never part of a public report.")


def install_schedule(_args):
    config = load()
    if not config.get("enabled"):
        raise ValueError("Connect first")
    gh_path = shutil.which("gh")
    if not gh_path:
        raise ValueError("Install GitHub CLI first")
    env = {"PATH": str(pathlib.Path(gh_path).parent) + os.pathsep + os.environ.get("PATH", "")}
    if os.environ.get("XDG_CONFIG_HOME"):
        env["XDG_CONFIG_HOME"] = os.environ["XDG_CONFIG_HOME"]
    command = [sys.executable, "-m", "arena.client", "run"]
    if sys.platform == "darwin":
        agent = pathlib.Path.home() / "Library/LaunchAgents/cc.sparkarena.reporter.plist"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        plist = {"Label": "cc.sparkarena.reporter", "ProgramArguments": command,
                 "WorkingDirectory": str(ROOT), "StartInterval": 3600, "RunAtLoad": True,
                 "EnvironmentVariables": env,
                 "StandardOutPath": str(CONFIG_DIR / "reporter.log"),
                 "StandardErrorPath": str(CONFIG_DIR / "reporter-error.log")}
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_bytes(plistlib.dumps(plist))
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(agent)], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(agent)], check=True)
    elif sys.platform.startswith("linux"):
        target = pathlib.Path.home() / ".config/systemd/user"
        target.mkdir(parents=True, exist_ok=True)
        # systemd quoted arguments cannot contain newlines/quotes; reject exotic paths.
        values = [str(ROOT), *command, *env.values()]
        if any(any(c in v for c in '\n\r"%\\') for v in values):
            raise ValueError("Unsupported scheduler path; use cron/manual scheduler as described in README")
        environment = ''.join(f'Environment="{key}={value}"\n' for key,value in env.items())
        service = ("[Unit]\nDescription=Spark Arena daily reporter\n[Service]\nType=oneshot\n"
                   f'WorkingDirectory="{ROOT}"\n' + environment +
                   'ExecStart=' + ' '.join('"' + v + '"' for v in command) + '\n')
        (target / "spark-arena.service").write_text(service)
        (target / "spark-arena.timer").write_text("[Unit]\nDescription=Check daily sparkDash report hourly\n"
            "[Timer]\nOnBootSec=2min\nOnUnitActiveSec=1h\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "spark-arena.timer"], check=True)
    else:
        raise ValueError("Use Windows Task Scheduler; see README for exact command")
    print("Hourly retry installed. Uploads yesterday once, then skips unchanged data. Keep this clone in place.")
    print("A token saved by the 'token' command works in the scheduler; shell-only env vars do not persist.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("connect", help="Read PRIVACY.md; explicitly opt in to public reporting")
    p.add_argument("--name", required=True, help="Public WeChat display nickname, not WeChat ID")
    p.add_argument("--url", required=True, help="Local/private sparkDash base URL")
    p.add_argument("--repo", default="OWAngel/token-arena")
    auth = p.add_mutually_exclusive_group()
    auth.add_argument("--token-file")
    auth.add_argument("--token-env-file", help="Read existing private .env literally; never execute it or copy its credentials")
    p.add_argument("--consent-public", action="store_true")
    p.set_defaults(func=connect)
    p = sub.add_parser("run", help="Upload yesterday, or preview without publishing")
    p.add_argument("--date", help="YYYY-MM-DD within upstream hourly retention")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=run)
    for command, fn in (("leave", leave), ("token", save_token), ("install-schedule", install_schedule)):
        sub.add_parser(command).set_defaults(func=fn)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # Exception strings are sanitized by each network wrapper.
        print("Error:", exc if isinstance(exc, ValueError) else "Local file or scheduler operation failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
