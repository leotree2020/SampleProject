#include "parser.h"
#include <string.h>

int parse_record(const unsigned char *input, size_t len)
{
    unsigned char buf[16];

    if (len < 1) {
        return -1;
    }

    unsigned char n = input[0];

    /* Reject records that would overflow `buf` or read past the input. */
    if (n > sizeof(buf)) {
        return -1;
    }
    if ((size_t)n > len - 1) {
        return -1;
    }

    memcpy(buf, input + 1, n);

    int sum = 0;
    for (unsigned i = 0; i < n; i++) {
        sum = (sum + buf[i]) & 0xff;
    }
    return sum;
}
