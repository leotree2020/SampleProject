#include "parser.h"
#include <stddef.h>

/*
 * Optional libFuzzer harness (requires clang with -fsanitize=fuzzer).
 * Build, e.g.:
 *   clang -fsanitize=fuzzer,address,undefined -Iinclude \
 *       vuln/parser.c harness/fuzz_harness.c -o build/fuzz_vuln
 *   ./build/fuzz_vuln -runs=100000
 * The fuzzer should rediscover the overflow within a handful of inputs, since
 * any first byte > 16 triggers it.
 */
int LLVMFuzzerTestOneInput(const unsigned char *data, size_t size)
{
    parse_record(data, size);
    return 0;
}
