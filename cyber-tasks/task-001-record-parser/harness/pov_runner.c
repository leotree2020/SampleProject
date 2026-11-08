#include "parser.h"
#include <stdio.h>

/*
 * Feeds a single input file to parse_record(). Used by the verifier to replay
 * the proof-of-vulnerability against both builds.
 */
int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <input-file>\n", argv[0]);
        return 2;
    }

    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        perror("fopen");
        return 2;
    }

    static unsigned char buf[65536];
    size_t n = fread(buf, 1, sizeof(buf), f);
    fclose(f);

    int r = parse_record(buf, n);
    printf("parse_record returned %d\n", r);
    return 0;
}
