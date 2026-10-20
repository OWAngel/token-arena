# Spark Arena contributor instructions

- Scope: only MiaAI-Lab/sparkDash. Participants explicitly opt in on their own machines.
- Commands: `python3 -m unittest discover -s tests -v`; `node --test tests/*.test.js`;
  `python3 -m arena.build --repo OWAngel/token-arena`.
- `arena/core.py`: public allowlist and token invariants; `sparkdash.py`: local GET adapter;
  `client.py`: explicit enrollment, reporting, scheduler, withdrawal;
  `build.py`: current Issues -> public JSON; `web/`: static interactive board.
- Never publish endpoint URLs, auth tokens, hardware/node identifiers, prompts, complete history responses,
  local configuration, environment files, screenshots of private sources, or real user test data.
- Input includes cache. Total = input + output; never add cached input twice.
- Upstream UTC hour buckets must be selected for Asia/Shanghai calendar days. Never substitute rolling
  24h or UTC daily totals. Expired hourly history must fail rather than estimate.
- A closed enrollment hides all reports; closed daily reports must not auto-reopen. Use numeric GitHub
  author identity, never a body-provided login. Untrusted issue content must never enter shell commands.
- Use synthetic fixtures for tests. Do not enroll the operator or publish a real report as a test.
- Do not edit the local sparkDash project or change its deployment to implement this integration.
- Scope code-review agents to this repository only; no unrelated private repository scanning.
