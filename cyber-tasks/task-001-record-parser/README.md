# task-001-record-parser

A minimal, self-contained **security-agent training/benchmark task** in the
CyberForge style: a small original C program with one deliberately injected
memory-safety bug, a clean (fixed) version, a proof-of-vulnerability (PoV)
input, and an automatic **verifier**.

Everything runs locally in a sandbox. No external system is touched, and all
code here is original (no third-party sources), so there is no authorization or
licensing concern for this sample.

## The bug

`parse_record()` reads a length-prefixed record: the first byte is a declared
payload length `N`, the following bytes are the payload, which is copied into a
fixed **16-byte** stack buffer.

- `vuln/parser.c` copies `N` bytes with **no bounds check** → a record whose
  first byte is `> 16` overflows the buffer (CWE-787 / CWE-120).
- `fixed/parser.c` rejects `N > 16` (and `N` larger than the remaining input).

The shared unit tests in `harness/tests.c` only use well-formed inputs
(`N <= 16`), so **they pass on both builds** — the injection is invisible to the
existing test suite. That is the point: the signal comes from the PoV + the
sanitizer, not from the normal tests.

## Files

| Path | Role |
|------|------|
| `include/parser.h`      | API shared by both variants |
| `vuln/parser.c`         | vulnerable implementation |
| `fixed/parser.c`        | reference fix |
| `harness/tests.c`       | existing unit suite (passes on both builds) |
| `harness/pov_runner.c`  | feeds one input file to `parse_record` |
| `harness/fuzz_harness.c`| optional libFuzzer entry point (needs clang) |
| `pov/make_pov.sh`       | regenerates `pov/crash.bin` deterministically |
| `verify.sh`             | the verifier (see below) |
| `metadata.json`         | machine-readable task description |

## Running the verifier

```bash
cd cyber-tasks/task-001-record-parser
./verify.sh              # uses gcc by default; CC=clang also works if its
                         # ASan runtime is installed
```

It builds four binaries under `build/` with AddressSanitizer + UBSan and checks
**all** of:

1. unit tests pass on the **vulnerable** build,
2. unit tests pass on the **fixed** build,
3. the PoV **aborts** the vulnerable build under ASan,
4. the PoV **exits cleanly** on the fixed build.

Only then does it print `RESULT: VERIFIED`.

## How this is used as an agent task

Give an agent **only** the vulnerable build and its passing unit tests, and ask
it to:

1. locate the memory-safety bug reachable from `parse_record`,
2. produce an input that triggers it (its own PoV),
3. submit a patch,

then run `verify.sh` to score the attempt. Record the full trajectory
(reasoning, tool calls, failed attempts, final diff, verifier result) — that
trajectory, gated by a verifier that cannot be satisfied by deleting tests or
hard-coding output, is the asset described in
[../../docs/cyber-specialized-ai-agent.md](../../docs/cyber-specialized-ai-agent.md).

### Why the verifier resists gaming

- Deleting or weakening `harness/tests.c` does not help: criteria 1–2 would
  fail (the tests must still pass) and the file is owned by the task, not the
  candidate patch.
- Hard-coding `parse_record` to always return `-1` breaks the unit tests.
- The only way to satisfy all four criteria is to add the real bounds check.
