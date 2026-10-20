"""GitHub public Issues are the authenticated, auditable opt-in transport."""
import json
import re
import subprocess


def gh(args, data=None):
    try:
        result = subprocess.run(["gh", *args], input=data, text=True, capture_output=True,
                                timeout=60, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise ValueError("Install GitHub CLI and run gh auth login, or retry after network recovery") from None
    if result.returncode:
        # Do not echo raw stderr: it can contain request bodies or private endpoint data.
        raise ValueError("GitHub operation failed; check gh auth status, repository, and network")
    return json.loads(result.stdout) if result.stdout.strip() else None


def repo_name(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Repository must be owner/name")
    return value


def issues(repo):
    pages = gh(["api", "--paginate", "--slurp", f"repos/{repo_name(repo)}/issues?state=all&per_page=100"])
    return [x for page in pages for x in page if "pull_request" not in x]


def write_issue(repo, title, body, number=None):
    path = f"repos/{repo_name(repo)}/issues" + (f"/{int(number)}" if number else "")
    return gh(["api", "--method", "PATCH" if number else "POST", path, "--input", "-"],
              json.dumps({"title": title, "body": body}))


def set_state(repo, number, state):
    return gh(["api", "--method", "PATCH", f"repos/{repo_name(repo)}/issues/{int(number)}", "--input", "-"],
              json.dumps({"state": state}))
