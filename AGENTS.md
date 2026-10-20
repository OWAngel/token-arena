# Spark Arena contributor instructions

- Scope: only MiaAI-Lab/sparkDash. Participants explicitly opt in on their own machines.
- Commands: `python3 -m unittest discover -s tests -v`; `node --test tests/*.test.js`;
  `python3 -m arena.build --repo OWAngel/token-arena`.
- Default participation is the account-free `platform/` website and `arena.platform_client` reporter. Do not require GitHub or WeChat accounts, or reintroduce a separate voluntary checkbox. Browsing/filling is not enrollment; the active join action is required. Management credentials and source addresses stay private.
- `arena/core.py`: public allowlist and token invariants; `sparkdash.py`: local GET adapter;
  `client.py`: explicit enrollment, reporting, scheduler, withdrawal;
  `build.py`: current Issues -> public JSON; `web/`: static interactive board.
- Never publish endpoint URLs, auth tokens, hardware/node identifiers, prompts, complete history responses,
  local configuration, environment files, screenshots of private sources, or real user test data.
- Input includes cache. Total = input + output; never add cached input twice.
- Upstream UTC hour buckets must be selected for Asia/Shanghai calendar days. Never substitute rolling
  24h or UTC daily totals. Expired hourly history must fail rather than estimate.
- A closed enrollment hides all reports; closed daily reports must not auto-reopen. For the legacy GitHub channel use numeric GitHub
  author identity, never a body-provided login. Platform identities are server-generated random IDs. Untrusted issue content must never enter shell commands.
- Use synthetic fixtures for tests. Do not enroll the operator or publish a real report as a test.
- Do not edit the local sparkDash project or change its deployment to implement this integration.
- Scope code-review agents to this repository only; no unrelated private repository scanning.
