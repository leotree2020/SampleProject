#!/usr/bin/env python3
"""
reproduce.py -- "reproduce before you submit" harness for source-available C/C++
targets.

Given a target source file you are authorized to test (open-source you can
clone, or an in-scope program's source), a small driver that feeds one input
file to the entry point, and a candidate crashing input, this:

    1. builds the target + driver with AddressSanitizer / UBSan,
    2. confirms the input actually crashes it, and classifies the crash,
    3. minimizes the input (ddmin) down to the smallest bytes that still crash,
    4. writes a DRAFT submission report + the minimized PoC, and
    5. records the whole thing as a trajectory (trajectory.py).

The point: never submit a finding that this harness could not reproduce. That
is exactly what 2026 bounty platforms now require (a human-validated,
reproducible report), and it is what makes your reports stand out from AI slop.

ETHICS / SCOPE
    Only point this at code you are authorized to test: open source you can
    clone, your own software, or a program whose scope explicitly covers it.
    This runs the target's own code locally under a sanitizer; it does not and
    must not touch any live third-party system. Confirm authorization and scope
    before acting on any output.

Example (uses task-001's vulnerable parser as a stand-in source-available
target, with its pov_runner as the driver):

    python3 reproduce.py \
        --target ../task-001-record-parser/vuln/parser.c \
        --driver ../task-001-record-parser/harness/pov_runner.c \
        --include ../task-001-record-parser/include \
        --input  ../task-001-record-parser/pov/crash.bin \
        --out reports/demo --minimize
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

from trajectory import TrajectoryRecorder

CC = os.environ.get("CC", "gcc")
SAN = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-g", "-O1"]

# crash signature -> (label, suspected CWEs)
CWE_HINTS = [
    (re.compile(r"AddressSanitizer:\s*heap-buffer-overflow"),
     ("heap buffer overflow", "CWE-122 / CWE-787 / CWE-125")),
    (re.compile(r"AddressSanitizer:\s*stack-buffer-overflow"),
     ("stack buffer overflow", "CWE-121 / CWE-787")),
    (re.compile(r"AddressSanitizer:\s*global-buffer-overflow"),
     ("global buffer overflow", "CWE-787")),
    (re.compile(r"AddressSanitizer:\s*heap-use-after-free"),
     ("use after free", "CWE-416")),
    (re.compile(r"AddressSanitizer:\s*(?:attempting )?double-free"),
     ("double free", "CWE-415")),
    (re.compile(r"AddressSanitizer:\s*SEGV|SUMMARY:.*SEGV|signal 11"),
     ("null/invalid pointer dereference", "CWE-476 / CWE-787")),
    # ASan sometimes names the access category "unknown-crash" for an
    # out-of-bounds access it cannot attribute to a specific redzone; the
    # WRITE/READ-of-size line is the real signal.
    (re.compile(r"WRITE of size \d+"),
     ("out-of-bounds write", "CWE-787")),
    (re.compile(r"READ of size \d+"),
     ("out-of-bounds read", "CWE-125")),
    (re.compile(r"stack smashing detected"),
     ("stack smashing (canary)", "CWE-787 / CWE-121")),
    (re.compile(r"buffer overflow detected"),
     ("buffer overflow (_FORTIFY_SOURCE)", "CWE-120 / CWE-787")),
    (re.compile(r"runtime error:.*signed integer overflow"),
     ("signed integer overflow", "CWE-190")),
    (re.compile(r"runtime error:.*index .* out of bounds"),
     ("out-of-bounds index", "CWE-125 / CWE-787")),
    (re.compile(r"runtime error:"),
     ("undefined behaviour (UBSan)", "CWE-758")),
]


def run(cmd, cwd=None, inp=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, input=inp)


def classify(output: str) -> tuple[str, str]:
    for rx, (label, cwe) in CWE_HINTS:
        if rx.search(output):
            return label, cwe
    return "unknown crash", "CWE-unknown"


def first_error_lines(output: str, n: int = 12) -> str:
    lines = output.splitlines()
    for i, ln in enumerate(lines):
        if ("ERROR: AddressSanitizer" in ln or "runtime error:" in ln
                or "detected" in ln):
            return "\n".join(lines[i:i + n])
    return "\n".join(lines[:n])


def hexdump(data: bytes, width: int = 16) -> str:
    out = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{off:08x}  {hexs:<{width*3}}  {text}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, help="source-available target .c")
    ap.add_argument("--driver", required=True,
                    help="driver .c with a main() that reads argv[1] and calls the entry")
    ap.add_argument("--include", action="append", default=[], help="include dir (repeatable)")
    ap.add_argument("--input", required=True, help="candidate crashing input file")
    ap.add_argument("--out", default="reports/repro", help="output directory for report + PoC")
    ap.add_argument("--minimize", action="store_true", help="shrink the input while it still crashes")
    ap.add_argument("--model", default="scripted:reproduce", help="label for the trajectory")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    traj_path = os.path.join(args.out, "trajectory.jsonl")
    incs = []
    for d in args.include:
        incs += [f"-I{d}"]

    work = tempfile.mkdtemp(prefix="repro-")
    repro_bin = os.path.join(work, "repro")

    with TrajectoryRecorder(traj_path, task_id=os.path.basename(args.target),
                            model=args.model,
                            extra={"tool": "reproduce.py", "cc": CC}) as rec:
        # --- build ---
        rec.step("explore", "build target under sanitizers", tool="compile",
                 tool_input=f"{args.target} + {args.driver}")
        cp = run([CC, *SAN, *incs, args.target, args.driver, "-o", repro_bin])
        if cp.returncode != 0:
            rec.step("explore", "build failed", tool="compile", status="error",
                     tool_output_summary=cp.stderr[-500:])
            rec.score(result="UNSOLVED", criteria={"built": False, "reproduced": False})
            rec.end(result="UNSOLVED")
            print("BUILD FAILED:\n" + cp.stderr[-800:])
            shutil.rmtree(work, ignore_errors=True)
            return 2

        def crashes(data: bytes) -> tuple[bool, str]:
            tf = os.path.join(work, "candidate.bin")
            with open(tf, "wb") as f:
                f.write(data)
            r = run([repro_bin, tf])
            out = (r.stdout or "") + (r.stderr or "")
            return (r.returncode != 0), out

        data = open(args.input, "rb").read()
        did_crash, out = crashes(data)
        if not did_crash:
            rec.step("verify", "replay candidate input", tool="run",
                     status="fail", tool_output_summary="did NOT crash")
            rec.score(result="UNSOLVED", criteria={"built": True, "reproduced": False},
                      note="input does not reproduce a crash on this build")
            rec.end(result="UNSOLVED")
            print("NOT REPRODUCED: the input did not crash the target.")
            shutil.rmtree(work, ignore_errors=True)
            return 1

        label, cwe = classify(out)
        rec.step("verify", "crash reproduced", tool="run", status="ok",
                 tool_output_summary=f"{label} ({len(data)} bytes)")

        # --- minimize (ddmin-style chunk removal) ---
        if args.minimize:
            n = 2
            while len(data) >= 2 and n <= len(data):
                chunk = max(1, len(data) // n)
                i = 0
                reduced = False
                while i < len(data):
                    trial = data[:i] + data[i + chunk:]
                    if trial and crashes(trial)[0]:
                        data = trial
                        reduced = True
                        # keep same granularity, retry at same position
                    else:
                        i += chunk
                if reduced:
                    n = max(n - 1, 2)
                else:
                    if chunk == 1:
                        break
                    n = min(len(data), n * 2)
            _, out = crashes(data)  # refresh sanitizer output for the minimized PoC
            label, cwe = classify(out)
            rec.step("verify", "minimized PoC", tool="minimize", status="ok",
                     tool_output_summary=f"{len(data)} bytes")

        # --- write report + PoC ---
        poc_path = os.path.join(args.out, "poc.bin")
        with open(poc_path, "wb") as f:
            f.write(data)

        excerpt = first_error_lines(out)
        report = f"""# [DRAFT] {label} in {os.path.basename(args.target)}

> AUTO-GENERATED DRAFT (reproduce.py). Before submitting anywhere, a human must:
> verify the target is **in scope / authorized**, assess real-world impact and
> reachability from attacker-controlled input, follow the program's AI-tool
> disclosure rules, and remove this banner.

## Summary

A `{label}` ({cwe}) is reachable in `{os.path.basename(args.target)}` and
reproduces deterministically under AddressSanitizer/UBSan with a {len(data)}-byte
input.

## Affected

- target source: `{args.target}`
- driver / entry: `{args.driver}`
- build: `{CC} {' '.join(SAN)} {' '.join(incs)}`

## Crash

- detector: {label}
- suspected weakness: {cwe}

```
{excerpt}
```

## Reproduction

1. Build:
   ```
   {CC} {' '.join(SAN)} {' '.join(incs)} {args.target} {args.driver} -o repro
   ```
2. Run against the attached PoC:
   ```
   ./repro poc.bin
   ```
3. Observe the sanitizer abort shown above.

Minimized PoC ({len(data)} bytes, saved as `poc.bin`):

```
{hexdump(data)}
```

## Impact / next steps (fill in before submitting)

- Confirm the vulnerable function is reachable from real, attacker-controlled
  input in the deployed product (not only via this driver).
- Assess severity (crash vs. exploitable write) and draft a fix.
- Check the program's scope and AI-assistance disclosure policy.
"""
        report_path = os.path.join(args.out, "report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        rec.score(result="SOLVED",
                  criteria={"built": True, "reproduced": True,
                            "minimized": bool(args.minimize)},
                  note=f"{label}; {len(data)} byte PoC")
        rec.end(result="SOLVED")

    shutil.rmtree(work, ignore_errors=True)
    print(f"REPRODUCED : {label} ({cwe})")
    print(f"PoC        : {poc_path} ({len(data)} bytes)")
    print(f"report     : {report_path}")
    print(f"trajectory : {traj_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
