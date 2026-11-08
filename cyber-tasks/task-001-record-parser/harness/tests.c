#include "parser.h"
#include <stdio.h>

/*
 * Shared unit tests. These are the project's *existing* test suite and must
 * pass on BOTH the vulnerable and the fixed build. Crucially, they only use
 * well-formed inputs (declared length <= 16), so the injected overflow is
 * invisible here -- which is the whole point: a stealthy injection does not
 * disturb the existing tests.
 */

static int failures = 0;

static void check(const char *name, int got, int want)
{
    if (got != want) {
        printf("FAIL %s: got %d, want %d\n", name, got, want);
        failures++;
    } else {
        printf("ok   %s\n", name);
    }
}

int main(void)
{
    /* empty input -> malformed */
    check("empty", parse_record((const unsigned char *)"", 0), -1);

    /* n = 0 -> checksum 0 */
    {
        unsigned char in[] = {0};
        check("n=0", parse_record(in, 1), 0);
    }

    /* small valid record: 10 + 20 + 30 = 60 */
    {
        unsigned char in[] = {3, 10, 20, 30};
        check("n=3", parse_record(in, 4), 60);
    }

    /* checksum wraps mod 256: (200 + 100) & 0xff = 44 */
    {
        unsigned char in[] = {2, 200, 100};
        check("wrap", parse_record(in, 3), (200 + 100) & 0xff);
    }

    /* boundary: n = 16 exactly fills the buffer and is still valid */
    {
        unsigned char in[17];
        in[0] = 16;
        for (int i = 1; i < 17; i++) {
            in[i] = 1;
        }
        check("n=16 boundary", parse_record(in, 17), 16);
    }

    if (failures) {
        printf("%d test(s) failed\n", failures);
        return 1;
    }
    printf("all tests passed\n");
    return 0;
}
