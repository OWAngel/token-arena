#!/usr/bin/env sh
# Development checks only. Does not enroll, upload, install a scheduler, or read secrets.
set -eu
cd "$(dirname "$0")"
python3 -m unittest discover -s tests -v
node --test tests/*.test.js
printf '%s\n' 'Checks passed. Read README.md and PRIVACY.md before opting in.'
