"""Spark Arena local reporter. No GitHub/WeChat account required."""
import argparse
import functools
import subprocess
import sys

from . import wechat_client as device
from .client import CONFIG_DIR

CONFIG = CONFIG_DIR / "platform.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    bind = commands.add_parser("bind")
    bind.add_argument("--api-base", required=True)
    bind.add_argument("--url", required=True)
    auth = bind.add_mutually_exclusive_group()
    auth.add_argument("--token-file")
    auth.add_argument("--token-env-file")
    # Active use of the bind command is the participant's enrollment action.
    bind.set_defaults(consent_public=True, func=functools.partial(device.bind,
        config_path=CONFIG, label="Spark Arena", module="arena.platform_client"))
    run = commands.add_parser("run")
    run.add_argument("--date")
    run.add_argument("--preview", action="store_true")
    run.set_defaults(func=functools.partial(device.run, config_path=CONFIG, label="Spark Arena"))
    commands.add_parser("pause").set_defaults(func=functools.partial(device.pause, config_path=CONFIG))
    commands.add_parser("install-schedule").set_defaults(func=functools.partial(device.install_schedule,
        config_path=CONFIG, module="arena.platform_client", channel="platform"))
    args = parser.parse_args()
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
