#!/usr/bin/env python3
"""
fuzz.py -- the front of the pipeline: find candidate crashing inputs in a
source-available C/C++ target, dedup them, and (optionally) hand each unique
crash to reproduce.py for minimization + a DRAFT report.

    seeds --> [ fuzz.py ] --> crashing inputs --> [ reproduce.py ] --> report + PoC

Engines:
  builtin   (default) a dependency-free mutational fuzzer that drives a file
            -reading driver built with gcc + ASan/UBSan. Works anywhere gcc
            does. It is COVERAGE-BLIND -- good for shallow bugs and smoke
            testing, not a substitute for a real coverage-guided campaign.
  libfuzzer uses clang's -fsanitize=fuzzer on the target's LLVMFuzzerTestOneInput
            (needs clang + compiler-rt fuzzer/asan runtimes installed). Use this
            for real campaigns where the runtime is available.

ETHICS / SCOPE
    Only fuzz code you are authorized to test: open source you can clone, your
    own code, or a program whose scope explicitly covers it. This builds and
    runs the target's own code locally under a sanitizer; it never touches a
    live third-party system.

Example (builtin, against task-001; finds the overflow in well under a second):

    python3 fuzz.py \
        --target ../task-001-record-parser/vuln/parser.c \
        --driver ../task-001-record-parser/harness/pov_runner.c \
        --include ../task-001-record-parser/include \
        --seconds 10 --reproduce
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

from trajectory import TrajectoryRecorder
from reproduce import classify, CC, SAN  # reuse crash classification + build flags

RUN_ENV = dict(os.environ,
               ASAN_OPTIONS="abort_on_error=1:detect_leaks=0:exitcode=134",
               UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=0")

INTERESTING = [0x00, 0x01, 0x07, 0x08, 0x0f, 0x10, 0x11, 0x1f, 0x20,
               0x3f, 0x40, 0x7e, 0x7f, 0x80, 0x81, 0xfe, 0xff]


def norm_sig(output: str) -> str:
    """Collapse addresses/line noise so the same bug dedups to one signature."""
    label, _ = classify(output)
    # keep the SUMMARY line if present, else the first error line
    key = label
    m = re.search(r"SUMMARY:.*", output)
    if m:
        key = m.group(0)
    key = re.sub(r"0x[0-9a-f]+", "0xADDR", key)
    key = re.sub(r"\b\d{3,}\b", "N", key)
    return label, hashlib.sha1(key.encode()).hexdigest()[:10]


def mutate(seed: bytes, max_len: int) -> bytes:
    b = bytearray(seed) if seed else bytearray(b"\x00")
    for _ in range(random.randint(1, 5)):
        op = random.random()
        if not b:
            b = bytearray(b"\x00")
        if op < 0.25:                                   # flip a bit
            i = random.randrange(len(b))
            b[i] ^= 1 << random.randrange(8)
        elif op < 0.45:                                 # interesting byte
            b[random.randrange(len(b))] = random.choice(INTERESTING)
        elif op < 0.60:                                 # random byte
            b[random.randrange(len(b))] = random.randrange(256)
        elif op < 0.75 and len(b) < max_len:            # insert
            i = random.randrange(len(b) + 1)
            b[i:i] = bytes(random.randrange(256)
                           for _ in range(random.randint(1, 8)))
        elif op < 0.88 and len(b) > 1:                  # delete chunk
            i = random.randrange(len(b))
            n = random.randint(1, min(8, len(b) - i))
            del b[i:i + n]
        else:                                           # duplicate chunk
            if len(b) < max_len:
                i = random.randrange(len(b))
                n = random.randint(1, min(16, len(b) - i))
                b[i:i] = b[i:i + n]
    return bytes(b[:max_len])


def default_seeds() -> list[bytes]:
    return [b"", b"\x00", b"\x01\x00", b"\x04\x01\x02\x03\x04",
            b"\x10" + b"\x01" * 16, bytes(range(8))]


def load_seeds(path: str | None) -> list[bytes]:
    if not path:
        return default_seeds()
    seeds = []
    for name in sorted(os.listdir(path)):
        fp = os.path.join(path, name)
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                seeds.append(f.read())
    return seeds or default_seeds()


def builtin_campaign(repro_bin, seeds, seconds, max_len, crashes_dir, rec):
    os.makedirs(crashes_dir, exist_ok=True)
    seen: dict[str, str] = {}
    execs = 0
    deadline = time.time() + seconds
    tmp = tempfile.NamedTemporaryFile(prefix="fz-", delete=False).name
    corpus = [s for s in seeds]

    while time.time() < deadline:
        seed = random.choice(corpus)
        data = mutate(seed, max_len)
        with open(tmp, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run([repro_bin, tmp], capture_output=True, text=True,
                               env=RUN_ENV, timeout=1.0)
        except subprocess.TimeoutExpired:
            execs += 1
            continue
        execs += 1
        if r.returncode != 0:
            label, sig = norm_sig((r.stdout or "") + (r.stderr or ""))
            if sig not in seen:
                dst = os.path.join(crashes_dir, f"crash-{sig}.bin")
                with open(dst, "wb") as f:
                    f.write(data)
                seen[sig] = dst
                rec.step("fuzz", f"new unique crash: {label}", tool="fuzz",
                         tool_output_summary=f"{len(data)} bytes -> {os.path.basename(dst)}")
    os.unlink(tmp)
    return execs, seen


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, help="source-available target .c")
    ap.add_argument("--driver", help="file-reading driver .c (builtin engine)")
    ap.add_argument("--fuzz-harness", help="LLVMFuzzerTestOneInput .c (libfuzzer engine)")
    ap.add_argument("--include", action="append", default=[], help="include dir (repeatable)")
    ap.add_argument("--seeds", help="seed corpus directory (optional)")
    ap.add_argument("--engine", choices=["builtin", "libfuzzer"], default="builtin")
    ap.add_argument("--seconds", type=int, default=15, help="time budget")
    ap.add_argument("--max-input", type=int, default=4096, help="max input size (bytes)")
    ap.add_argument("--out", default="findings", help="output dir for crashes + reports")
    ap.add_argument("--reproduce", action="store_true",
                    help="run reproduce.py on each unique crash")
    ap.add_argument("--model", default="scripted:fuzz", help="trajectory label")
    args = ap.parse_args()

    incs = [f"-I{d}" for d in args.include]
    os.makedirs(args.out, exist_ok=True)
    crashes_dir = os.path.join(args.out, "crashes")
    traj_path = os.path.join(args.out, "fuzz-trajectory.jsonl")
    work = tempfile.mkdtemp(prefix="fuzz-")

    rc = 1
    with TrajectoryRecorder(traj_path, task_id=os.path.basename(args.target),
                            model=args.model,
                            extra={"engine": args.engine, "cc": CC,
                                   "seconds": args.seconds}) as rec:
        if args.engine == "libfuzzer":
            if not args.fuzz_harness:
                raise SystemExit("--engine libfuzzer requires --fuzz-harness")
            rec.step("fuzz", "build libfuzzer target", tool="compile")
            fb = os.path.join(work, "fuzz")
            cp = subprocess.run(
                ["clang", "-fsanitize=fuzzer,address,undefined", "-O1", "-g",
                 *incs, args.target, args.fuzz_harness, "-o", fb],
                capture_output=True, text=True)
            if cp.returncode != 0:
                rec.step("fuzz", "libfuzzer build failed", tool="compile",
                         status="error", tool_output_summary=cp.stderr[-400:])
                rec.end(result="ERROR")
                print("libFuzzer build failed (runtime likely not installed):\n"
                      + cp.stderr[-600:])
                shutil.rmtree(work, ignore_errors=True)
                return 2
            os.makedirs(crashes_dir, exist_ok=True)
            subprocess.run([fb, f"-max_total_time={args.seconds}",
                            f"-artifact_prefix={crashes_dir}/"], cwd=work)
            seen = {f: os.path.join(crashes_dir, f)
                    for f in os.listdir(crashes_dir)}
            execs = -1
        else:
            if not args.driver:
                raise SystemExit("--engine builtin requires --driver")
            rec.step("fuzz", "build target (gcc + ASan/UBSan)", tool="compile",
                     tool_input=f"{args.target} + {args.driver}")
            repro_bin = os.path.join(work, "repro")
            cp = subprocess.run([CC, *SAN, *incs, args.target, args.driver,
                                 "-o", repro_bin], capture_output=True, text=True)
            if cp.returncode != 0:
                rec.step("fuzz", "build failed", tool="compile", status="error",
                         tool_output_summary=cp.stderr[-400:])
                rec.end(result="ERROR")
                print("BUILD FAILED:\n" + cp.stderr[-600:])
                shutil.rmtree(work, ignore_errors=True)
                return 2
            seeds = load_seeds(args.seeds)
            execs, seen = builtin_campaign(repro_bin, seeds, args.seconds,
                                           args.max_input, crashes_dir, rec)

        n_unique = len(seen)
        rec.step("fuzz", "campaign finished", tool="fuzz",
                 tool_output_summary=f"execs={execs} unique_crashes={n_unique}")

        # chain into reproduce.py for minimization + reports
        reports = []
        if args.reproduce and args.driver:
            for sig, path in list(seen.items()):
                rep_out = os.path.join(args.out, "reports",
                                       os.path.basename(path).replace(".bin", ""))
                cp = subprocess.run(
                    [sys.executable, os.path.join(os.path.dirname(__file__), "reproduce.py"),
                     "--target", args.target, "--driver", args.driver,
                     *sum([["--include", d] for d in args.include], []),
                     "--input", path, "--out", rep_out, "--minimize"],
                    capture_output=True, text=True)
                ok = cp.returncode == 0
                rec.step("verify", f"reproduce+minimize {os.path.basename(path)}",
                         tool="reproduce.py", status="ok" if ok else "fail",
                         tool_output_summary=(cp.stdout.strip().splitlines()[0]
                                              if cp.stdout.strip() else cp.stderr[-200:]))
                if ok:
                    reports.append(os.path.join(rep_out, "report.md"))

        rec.score(result="CRASHES_FOUND" if n_unique else "NO_CRASH",
                  criteria={"crashes_found": bool(n_unique)},
                  note=f"{n_unique} unique")
        rec.end(result=f"{n_unique} unique crash(es)")
        rc = 0 if n_unique else 1

    shutil.rmtree(work, ignore_errors=True)
    print(f"engine     : {args.engine}")
    print(f"execs      : {execs if execs >= 0 else 'n/a'}")
    print(f"unique     : {len(seen)} crash signature(s) -> {crashes_dir}/")
    if args.reproduce and args.driver:
        for r in reports:
            print(f"report     : {r}")
    print(f"trajectory : {traj_path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
