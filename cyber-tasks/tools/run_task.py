#!/usr/bin/env python3
"""
Run one attempt at a cyber-task, score it, and record the full trajectory.

This is the agent-facing scorer (distinct from each task's verify.sh, which
checks the *task's own* integrity). Here we take a candidate patch for the
vulnerable file, build it with sanitizers, and reward it only when:

    1. the task's unit tests still pass on the patched build   (no regression)
    2. the proof-of-vulnerability no longer crashes it         (bug neutralized)

There is no live model in this harness, so candidates come from pluggable
"solvers" that stand in for an agent, or from a patch file:

    --solver oracle   use the task's fixed/ reference  -> should SOLVE
    --solver noop     leave the vulnerable code as-is   -> should stay UNSOLVED
    --solver gaming   replace the function with `return -1` (tries to dodge the
                      PoV by breaking behaviour) -> UNSOLVED, caught by tests
    --patch FILE      use FILE as the candidate parser.c

Every build/test/PoV action is written to the trajectory as a step, so the
same recorder is exercised whether the candidate comes from a script or a model.

Usage:
    python3 run_task.py --task ../task-001-record-parser --solver oracle
    python3 run_task.py --task ../task-001-record-parser --patch my_fix.c \
        --out trajectories/attempt.jsonl
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile

from trajectory import TrajectoryRecorder

CC = os.environ.get("CC", "gcc")
SAN = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-g", "-O1"]

GAMING_SRC = """\
#include "parser.h"
#include <stddef.h>

/* Gaming attempt: dodge the PoV by never doing the copy. Breaks real behaviour,
   so the unit tests fail and the attempt is correctly scored UNSOLVED. */
int parse_record(const unsigned char *input, size_t len)
{
    (void)input; (void)len;
    return -1;
}
"""


def run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def candidate_source(task: str, solver: str | None, patch: str | None) -> tuple[str, str]:
    """Return (source_text, origin)."""
    if patch:
        return read(patch), "file"
    if solver == "oracle":
        return read(os.path.join(task, "fixed", "parser.c")), "oracle"
    if solver == "gaming":
        return GAMING_SRC, "gaming"
    if solver == "noop":
        return read(os.path.join(task, "vuln", "parser.c")), "noop"
    raise SystemExit("provide --solver {oracle,noop,gaming} or --patch FILE")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, help="path to a task-NNN-* directory")
    ap.add_argument("--solver", choices=["oracle", "noop", "gaming"])
    ap.add_argument("--patch", help="candidate parser.c to score")
    ap.add_argument("--model", default=None, help="label recorded as the attempt's author")
    ap.add_argument("--out", default=None, help="trajectory JSONL path")
    args = ap.parse_args()

    task = os.path.abspath(args.task)
    task_id = os.path.basename(task.rstrip("/"))
    meta = os.path.join(task, "metadata.json")

    cand_src, origin = candidate_source(task, args.solver, args.patch)
    model = args.model or ("scripted:" + (args.solver or "file"))
    out = args.out or os.path.join("trajectories", f"{task_id}-{origin}.jsonl")

    base_vuln = read(os.path.join(task, "vuln", "parser.c"))
    diff = "".join(difflib.unified_diff(
        base_vuln.splitlines(keepends=True),
        cand_src.splitlines(keepends=True),
        fromfile="vuln/parser.c", tofile="candidate/parser.c"))

    work = tempfile.mkdtemp(prefix=f"{task_id}-{origin}-")
    inc = os.path.join(task, "include")
    harness = os.path.join(task, "harness")
    tests_pass = False
    pov_neutralized = False

    with TrajectoryRecorder(out, task_id=task_id, model=model,
                            task_metadata_path=meta,
                            extra={"origin": origin, "cc": CC}) as rec:
        rec.step("explore", "read vulnerable source", tool="read_file",
                 tool_input="vuln/parser.c",
                 tool_output_summary=f"{base_vuln.count(chr(10))} lines")

        # write candidate
        cand = os.path.join(work, "parser.c")
        with open(cand, "w", encoding="utf-8") as f:
            f.write(cand_src)
        rec.patch(target="vuln/parser.c", diff=diff or "(no change)", origin=origin)

        # ensure PoV input exists
        pov = os.path.join(task, "pov", "crash.bin")
        if not os.path.exists(pov):
            run(["bash", os.path.join(task, "pov", "make_pov.sh")], cwd=task)

        # --- criterion 1: build + run unit tests ---
        tests_bin = os.path.join(work, "tests")
        cp = run([CC, *SAN, f"-I{inc}", f"-I{harness}", cand,
                  os.path.join(harness, "tests.c"), "-o", tests_bin], cwd=work)
        if cp.returncode != 0:
            rec.step("verify", "compile tests", tool="compile", status="error",
                     tool_output_summary=cp.stderr[-400:])
        else:
            rec.step("verify", "compile tests", tool="compile", status="ok")
            tp = run([tests_bin], cwd=work)
            tests_pass = tp.returncode == 0
            rec.step("verify", "run unit tests", tool="run_tests",
                     status="ok" if tests_pass else "fail",
                     tool_output_summary=tp.stdout.strip().splitlines()[-1]
                     if tp.stdout.strip() else "(no output)")

        # --- criterion 2: PoV must no longer crash ---
        pov_bin = os.path.join(work, "pov_runner")
        cp = run([CC, *SAN, f"-I{inc}", f"-I{harness}", cand,
                  os.path.join(harness, "pov_runner.c"), "-o", pov_bin], cwd=work)
        if cp.returncode != 0:
            rec.step("verify", "compile pov runner", tool="compile", status="error",
                     tool_output_summary=cp.stderr[-400:])
        else:
            rec.step("verify", "compile pov runner", tool="compile", status="ok")
            pv = run([pov_bin, pov], cwd=work)
            pov_neutralized = pv.returncode == 0
            rec.step("verify", "replay proof-of-vulnerability", tool="run_pov",
                     tool_input="pov/crash.bin",
                     status="ok" if pov_neutralized else "fail",
                     tool_output_summary=("clean exit" if pov_neutralized
                                          else f"crashed (rc={pv.returncode})"))

        solved = tests_pass and pov_neutralized
        result = "SOLVED" if solved else "UNSOLVED"
        rec.score(result=result,
                  criteria={"tests_pass": tests_pass,
                            "pov_neutralized": pov_neutralized},
                  note=None if solved else "all criteria must hold to solve")
        rec.end(result=result)

    shutil.rmtree(work, ignore_errors=True)

    print(f"task      : {task_id}")
    print(f"candidate : {origin} (model={model})")
    print(f"tests_pass        = {tests_pass}")
    print(f"pov_neutralized   = {pov_neutralized}")
    print(f"RESULT    : {result}")
    print(f"trajectory: {out}")
    return 0 if result == "SOLVED" else 1


if __name__ == "__main__":
    sys.exit(main())
