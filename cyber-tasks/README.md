# cyber-tasks

Self-contained, verifiable security tasks for training and evaluating
security agents — the concrete, buildable counterpart to
[../docs/cyber-specialized-ai-agent.md](../docs/cyber-specialized-ai-agent.md).

Each task is a small program with:

- a **vulnerable** build and a **fixed** build,
- an existing test suite that passes on **both** (so an injected bug stays
  invisible to normal tests),
- a **proof-of-vulnerability** input, and
- a **verifier** (`verify.sh`) whose pass criteria cannot be satisfied by
  deleting tests or hard-coding output — only by the real fix.

The verifier is the product: it is what makes an agent's result trustworthy,
what gives a collected trajectory its value, and what a reinforcement-learning
environment is built around.

## Tasks

| ID | Language | Class | Difficulty |
|----|----------|-------|------------|
| [task-001-record-parser](./task-001-record-parser) | C | stack buffer overflow (CWE-787/120) | easy |

## Tooling

[`tools/`](./tools) runs an attempt at a task, scores the candidate patch
against a non-gameable verifier, and records the full **trajectory** as JSONL —
the data-collection loop that turns a solved task into a reusable asset. See
[tools/README.md](./tools/README.md) and [tools/SCHEMA.md](./tools/SCHEMA.md).

## Conventions

```
task-NNN-<slug>/
  README.md        human description + the exact agent task
  metadata.json    machine-readable: cwe, difficulty, entrypoint, pov, criteria
  include/         shared headers
  vuln/            vulnerable implementation
  fixed/           reference fix
  harness/         shared tests, pov runner, optional fuzz harness
  pov/             proof-of-vulnerability input + deterministic generator
  verify.sh        exit 0 == VERIFIED
  build/           (gitignored) verifier output
```

## Scope and ethics

- All code here is **original and self-contained**; no third-party code is
  copied in, so these samples carry no licensing or authorization concern.
- When adding tasks derived from real projects, only use code you are licensed
  to use, inject bugs into **your own copy**, and keep everything in the
  sandbox. Never point a PoV at a system you are not authorized to test.
- Vulnerabilities here are intentionally **toy and local** (crash-level, caught
  by a sanitizer). This is for building defensive training signal, not for
  producing weaponized exploits.
