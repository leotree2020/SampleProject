#ifndef PARSER_H
#define PARSER_H

#include <stddef.h>

/*
 * Parse a single length-prefixed record.
 *
 * Wire format:
 *   input[0]      = declared payload length N (0-255)
 *   input[1..N]   = payload bytes
 *
 * Returns an 8-bit checksum (0-255) of the payload on success, or -1 on
 * malformed input. The payload is copied into a fixed 16-byte internal
 * buffer before the checksum is computed.
 */
int parse_record(const unsigned char *input, size_t len);

#endif /* PARSER_H */
