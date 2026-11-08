# cyber-tasks/tools

The data-collection loop for the tasks in this directory tree: run an attempt
at a task, score it against a verifier that cannot be gamed, and record the
**full trajectory** as JSONL. The trajectory — not the final patch — is the
asset described in
[../../docs/cyber-specialized-ai-agent.md](../../docs/cyber-specialized-ai-agent.md).

```
Agent/solver runs task  →  scorer verifies  →  trajectory persisted  →  human review
        run_task.py                          trajectory.py / *.jsonl
```

## Files

| File | Role |
|------|------|
| `trajectory.py` | `TrajectoryRecorder`: append-only JSONL writer (stdlib only) |
| `run_task.py`   | scorer + recorder CLI (the agent-facing reward) |
| `SCHEMA.md`     | the trajectory format (v1.0) |
| `examples/`     | a committed reference trajectory |

## Scorer vs. task self-check

- Each task's **`verify.sh`** checks the *task's own* integrity (vuln is
  vulnerable, fixed is fixed, tests pass on both). Run by the task author.
- **`run_task.py`** scores an *agent's candidate patch* for the vulnerable
  file. A candidate SOLVES only when **both** hold:
  1. `tests_pass` — the task's unit tests still pass (no regression),
  2. `pov_neutralized` — the proof-of-vulnerability no longer crashes it.

Requiring both is what stops gaming: neutralizing the crash by breaking
behaviour fails criterion 1; leaving the bug in place fails criterion 2.

## Usage

```bash
cd cyber-tasks/tools

# stand-in "solvers" for an agent:
python3 run_task.py --task ../task-001-record-parser --solver oracle   # -> SOLVED
python3 run_task.py --task ../task-001-record-parser --solver noop     # -> UNSOLVED (still crashes)
python3 run_task.py --task ../task-001-record-parser --solver gaming   # -> UNSOLVED (tests fail)

# score a real candidate patch (a parser.c the agent produced):
python3 run_task.py --task ../task-001-record-parser --patch my_fix.c \
    --model claude-opus-4-8 --out trajectories/attempt-001.jsonl
```

Trajectories are written under `trajectories/` by default (gitignored). One
example run is committed under `examples/` so the format is concrete.

### Demonstrated outcomes

| solver | tests_pass | pov_neutralized | result |
|--------|------------|-----------------|--------|
| oracle | ✅ | ✅ | **SOLVED** |
| noop   | ✅ | ❌ | UNSOLVED |
| gaming | ❌ | ✅ | UNSOLVED |

## Wiring a real agent in

Replace the stand-in solvers with a model: have the agent read the vulnerable
source, propose a `parser.c`, and pass it via `--patch`. Record the agent's
own reasoning/tool-calls as `step` events (phase `explore`/`patch`) before the
scorer's `verify` steps. The recorder is already agnostic to whether steps come
from a script or a model, so nothing else changes.

> Note: when the attempt is driven by a hosted model, check that model's terms
> before reusing the resulting trajectory as training data for other systems —
> see the risks section of the monetization doc.
