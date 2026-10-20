"""Rebuild from current issue states; closed enrollment hides all of its reports."""
import argparse
import datetime as dt
import json
import pathlib
import shutil

from .core import parse_body
from .github import issues, repo_name


def compile_board(all_issues, repo):
    profiles, reports = {}, {}
    rejected = 0
    for issue in sorted(all_issues, key=lambda x: (x.get("updated_at", ""), x.get("number", 0))):
        try:
            payload = parse_body(issue.get("body"))
            user = issue["user"]
            if user.get("type") != "User":
                continue
            login = user["login"]
            # Numeric GitHub identity survives username changes; author cannot claim another user.
            uid = str(int(user["id"]))
            public = {"github": login, "id": uid, "issue": int(issue["number"]),
                      "updated_at": issue["updated_at"], **payload}
            if payload["kind"] == "participant":
                profiles[uid] = public if issue["state"] == "open" else None
            else:
                reports[(uid, payload["date"])] = public if issue["state"] == "open" else None
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
            rejected += 1
    active = {uid: p for uid, p in profiles.items() if p}
    rows = []
    for (uid, _), report in reports.items():
        if report and uid in active:
            rows.append({**report, "wechat_name": active[uid]["wechat_name"]})
    return {"version": 1, "repo": repo_name(repo), "timezone": "Asia/Shanghai",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "participants": [{k: p[k] for k in ("id", "github", "wechat_name", "issue")} for p in active.values()],
            "reports": sorted(rows, key=lambda x: (x["date"], x["id"])), "rejected_issues": rejected}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default="OWAngel/token-arena")
    p.add_argument("--output", default="dist")
    p.add_argument("--fixture", type=pathlib.Path)
    a = p.parse_args()
    data = json.loads(a.fixture.read_text()) if a.fixture else issues(a.repo)
    target = pathlib.Path(a.output)
    target.mkdir(parents=True, exist_ok=True)
    for file in pathlib.Path("web").iterdir():
        if file.is_file():
            shutil.copy2(file, target / file.name)
    (target / "data.json").write_text(json.dumps(compile_board(data, a.repo), ensure_ascii=False), encoding="utf-8")
    print("Built public board", target)


if __name__ == "__main__":
    main()
