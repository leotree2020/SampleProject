# Trajectory schema (v1.0)

A trajectory is an **append-only JSONL** file: one JSON object per line, in the
order events occurred. One file = one attempt at one task. The first line is
always `run_meta`; the last is always `run_end`.

All timestamps are ISO-8601 UTC. `seq` is a 1-based monotonic counter on every
event after `run_meta`.

## Event types

### `run_meta` (first line)
| field | meaning |
|-------|---------|
| `schema_version` | `"1.0"` |
| `run_id` | random 16-hex id for this attempt |
| `task_id` | e.g. `task-001-record-parser` |
| `model` | author of the attempt (e.g. `claude-opus-4-8`, or `scripted:oracle`) |
| `created_at` | start time |
| `task_metadata_sha256` | digest of the task's `metadata.json` (provenance) |
| `extra` | free-form object (e.g. `{"origin": "...", "cc": "gcc"}`) |

### `step`
One unit of work: a tool call, a decision, an observation.
| field | meaning |
|-------|---------|
| `phase` | `explore` \| `patch` \| `verify` |
| `action` | short human label |
| `tool` | `read_file` \| `compile` \| `run_tests` \| `run_pov` \| … \| `null` |
| `tool_input` | the argument given to the tool |
| `tool_output_summary` | short summary (never the full blob) |
| `status` | `ok` \| `fail` \| `error` |
| `note` | optional |

### `patch`
The candidate change under evaluation.
| field | meaning |
|-------|---------|
| `target` | file the patch applies to |
| `origin` | `model` \| `oracle` \| `file` \| `gaming` \| `noop` |
| `diff` | unified diff vs the vulnerable source |

### `score`
The verifier outcome.
| field | meaning |
|-------|---------|
| `result` | `SOLVED` \| `UNSOLVED` |
| `criteria` | object of booleans, e.g. `{"tests_pass": true, "pov_neutralized": true}` |
| `exit_code` | optional verifier exit code |
| `note` | optional |

### `human_review` (optional, added later)
A human-in-the-loop pass. This is the "verified" signal that makes a
trajectory worth more than an unverified one.
| field | meaning |
|-------|---------|
| `reviewer` | who |
| `verdict` | `confirmed` \| `rejected` \| `needs_work` |
| `notes` | optional |

### `run_end` (last line)
| field | meaning |
|-------|---------|
| `result` | final `SOLVED` \| `UNSOLVED` \| `ERROR` |
| `duration_s` | wall-clock seconds |

## Why this shape

- **Append-only + summaries, not blobs**: a trajectory stays small and
  streamable; raw outputs live in logs if needed, referenced by summary.
- **`criteria` is explicit**: the reward is auditable — you can see *why* an
  attempt scored as it did, which matters when selling verified data.
- **`task_metadata_sha256`**: ties each trajectory to the exact task version,
  so a dataset can't silently mix task revisions.
- **`human_review` is a first-class event**: verified vs unverified is the
  value distinction in the monetization docs.
