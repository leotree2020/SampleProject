#!/usr/bin/env bash
#
# Verifier for task-001-record-parser.
#
# Pass criteria (ALL must hold for the task to be VERIFIED):
#   1. The shared unit tests pass on BOTH the vulnerable and the fixed build
#      (the injected bug is invisible to the existing test suite).
#   2. The PoV input aborts the VULNERABLE build under AddressSanitizer.
#   3. The same PoV input exits cleanly on the FIXED build.
#
# This is the "verifier that cannot be trivially gamed" at the core of the
# task: it rewards a candidate patch only when the crash is gone AND the
# existing behaviour is preserved.
#
# Exit 0 = VERIFIED, non-zero otherwise. Override the compiler with CC=...
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

CC="${CC:-gcc}"
SAN="-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1"
INC="-Iinclude -Iharness"
build="$here/build"
rm -rf "$build"; mkdir -p "$build"

echo "== compiler: $($CC --version | head -1)"

fail() { echo; echo "RESULT: NOT VERIFIED ($1)"; exit 1; }

# --- build all four binaries --------------------------------------------------
$CC $SAN $INC vuln/parser.c  harness/tests.c      -o "$build/tests_vuln"  || fail "build tests_vuln"
$CC $SAN $INC fixed/parser.c harness/tests.c      -o "$build/tests_fixed" || fail "build tests_fixed"
$CC $SAN $INC vuln/parser.c  harness/pov_runner.c -o "$build/pov_vuln"    || fail "build pov_vuln"
$CC $SAN $INC fixed/parser.c harness/pov_runner.c -o "$build/pov_fixed"   || fail "build pov_fixed"

# --- ensure the PoV input exists ----------------------------------------------
[ -f pov/crash.bin ] || bash pov/make_pov.sh

# --- criterion 1: unit tests pass on both builds ------------------------------
echo "== unit tests (vulnerable build)"
"$build/tests_vuln"  || fail "unit tests failed on vulnerable build"
echo "== unit tests (fixed build)"
"$build/tests_fixed" || fail "unit tests failed on fixed build"

# --- criterion 2: PoV crashes the vulnerable build ----------------------------
echo "== PoV on vulnerable build (expected: AddressSanitizer abort)"
if "$build/pov_vuln" pov/crash.bin >"$build/pov_vuln.log" 2>&1; then
    cat "$build/pov_vuln.log"
    fail "PoV did NOT crash the vulnerable build"
fi
# The overflow is caught by AddressSanitizer and/or glibc _FORTIFY_SOURCE
# (__memcpy_chk), depending on compiler/flags; accept either as the signal.
grep -m1 -E 'AddressSanitizer|runtime error|buffer overflow detected|stack smashing' \
    "$build/pov_vuln.log" | sed 's/^/   /' || true
echo "   -> vulnerable build aborted as expected"

# --- criterion 3: PoV is handled safely by the fixed build --------------------
echo "== PoV on fixed build (expected: clean exit)"
if "$build/pov_fixed" pov/crash.bin >"$build/pov_fixed.log" 2>&1; then
    sed 's/^/   /' "$build/pov_fixed.log"
    echo "   -> fixed build handled the input safely"
else
    cat "$build/pov_fixed.log"
    fail "PoV crashed the FIXED build too"
fi

echo
echo "RESULT: VERIFIED"
