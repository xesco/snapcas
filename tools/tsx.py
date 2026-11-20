"""The reader of TSX files (docs/FORMATS.md, TSX data, and docs/internals/capture.md,
Tape files).

A TSX file is a TZX file with block 4Bh for MSX. The reader knows the blocks
that the TSX files of the tests use, and stops at any other. Times count the
pulses in T-states of 3.5 MHz, the TZX format's clock. tape.py makes the tape
model of the blocks that read() returns.
"""

SIGNATURE = b"ZXTape!\x1a"
T_STATES = 3500000

# Block 4Bh in the BIOS's format: 2 pulses for a 0 bit and 4 for a 1, 1 start
# bit 0, bit 0 first, and stop bits 1, 2 as the BIOS writes them or more, as
# After Burner's side B has 3: TAPIN waits for the next start bit. TAPION
# measures the header's tone to set its timing, so the pulses of a 0 bit can be
# from those of 2400 baud less 15% to those of 1200 baud plus 15%, as the tapes
# were recorded.
BIOS_BITS = 0x24
BIOS_ZERO = (729 * 0.85, 1458 * 1.15)


class TsxError(Exception):
    pass


def u(data, at, n):
    return int.from_bytes(data[at:at + n], "little")


def bits_time(data, zero, one, used=8):
    """The T-states of data's bits, most significant first, with used bits of
    the last byte, as the TZX blocks 10h and 11h send them: 2 pulses for each
    bit."""
    ones = sum(bin(b).count("1") for b in data[:-1]) if data else 0
    total = 8 * (len(data) - 1) + used if data else 0
    if data:
        ones += bin(data[-1] >> (8 - used)).count("1")
    return 2 * (ones * one + (total - ones) * zero)


def standard(body):
    """Whether a block 4Bh's body is in the BIOS's format."""
    zero, one = u(body, 10, 2), u(body, 12, 2)
    cfg = body[15]
    byte = cfg >> 6 == 1 and not cfg & 0x20 and (cfg >> 3) & 3 >= 2 and cfg & 0x04 and not cfg & 0x01
    return (body[14] == BIOS_BITS and bool(byte) and abs(zero - 2 * one) <= 0.05 * zero
            and BIOS_ZERO[0] <= zero <= BIOS_ZERO[1])


def kcs_time(body):
    """The T-states of a block 4Bh's pilot and bytes."""
    pilot, pilots, zero, one = (u(body, 6 + 2 * n, 2) for n in range(4))
    pulses0, pulses1 = body[14] >> 4 or 16, body[14] & 15 or 16
    cfg = body[15]
    starts, start_bit = cfg >> 6, (cfg >> 5) & 1
    stops, stop_bit = (cfg >> 3) & 3, (cfg >> 2) & 1
    framing = (starts * (pulses1 * one if start_bit else pulses0 * zero)
               + stops * (pulses1 * one if stop_bit else pulses0 * zero))
    data = body[16:]
    ones = sum(bin(b).count("1") for b in data)
    return pilot * pilots + len(data) * framing + ones * pulses1 * one + (8 * len(data) - ones) * pulses0 * zero


def _need(data, block, at, n):
    if at + n > len(data):
        raise TsxError(f"block {block:02X}h at {at - 1:X}h goes past the file's end")


def _append(found, data, is_standard, start, end, t, length):
    found.append((is_standard, bytes(data[start:end]), start, t / T_STATES, (t + length) / T_STATES))
    return t + length


def _read_speed_block(data, block, at, t, found):
    if block == 0x10:
        _need(data, block, at, 4)
        pause, n = u(data, at, 2), u(data, at + 2, 2)
        _need(data, block, at, 4 + n)
        body = data[at + 4:at + 4 + n]
        pilots = 8063 if body and body[0] < 128 else 3223
        t = _append(found, data, False, at + 4, at + 4 + n, t, pilots * 2168 + 667 + 735 + bits_time(body, 855, 1710))
        return at + 4 + n, t + pause * T_STATES // 1000
    _need(data, block, at, 18)
    pilot, sync1, sync2, zero, one, pilots = (u(data, at + 2 * k, 2) for k in range(6))
    used, pause, n = data[at + 12], u(data, at + 13, 2), u(data, at + 15, 3)
    _need(data, block, at, 18 + n)
    if used > 8:
        raise TsxError(f"block 11h at {at - 1:X}h uses {used} bits of its last byte")
    body = data[at + 18:at + 18 + n]
    t = _append(found, data, False, at + 18, at + 18 + n, t,
                pilots * pilot + sync1 + sync2 + bits_time(body, zero, one, used=used))
    return at + 18 + n, t + pause * T_STATES // 1000


def _read_kcs_block(data, at, t, found):
    _need(data, 0x4B, at, 4)
    n = u(data, at, 4)
    _need(data, 0x4B, at, 4 + n)
    if n < 12:
        raise TsxError(f"block 4Bh at {at - 1:X}h is shorter than its 12 bytes of settings")
    body = data[at:at + 4 + n]
    t = _append(found, data, standard(body), at + 16, at + 4 + n, t, kcs_time(body))
    return at + 4 + n, t + u(body, 4, 2) * T_STATES // 1000


# Metadata/grouping blocks with no signal: block_id -> (header_bytes, len_offset, len_size).
_SKIP_BLOCKS = {0x21: (1, 0, 1), 0x30: (1, 0, 1), 0x32: (2, 0, 2), 0x35: (20, 16, 4)}


def read(data):
    """The file's blocks that hold bytes or signal, as the fields of
    tape.Block: standard, the bytes, their offset in the file, and the
    player's seconds at the block's start and end."""
    if data[:8] != SIGNATURE:
        raise TsxError("not a TSX file: no ZXTape! signature")
    at, t, found = 10, 0, []
    while at < len(data):
        block, at = data[at], at + 1
        if block in (0x10, 0x11):
            at, t = _read_speed_block(data, block, at, t, found)
        elif block == 0x4B:
            at, t = _read_kcs_block(data, at, t, found)
        elif block == 0x12:
            _need(data, block, at, 4)
            t += u(data, at, 2) * u(data, at + 2, 2)
            at += 4
        elif block == 0x13:
            _need(data, block, at, 1)
            n = data[at]
            _need(data, block, at, 1 + 2 * n)
            t += sum(u(data, at + 1 + 2 * k, 2) for k in range(n))
            at += 1 + 2 * n
        elif block == 0x15:
            _need(data, block, at, 8)
            sample, pause, used, n = u(data, at, 2), u(data, at + 2, 2), data[at + 4], u(data, at + 5, 3)
            _need(data, block, at, 8 + n)
            t = _append(found, data, False, at + 8, at + 8, t, sample * (8 * max(n - 1, 0) + used))
            t += pause * T_STATES // 1000
            at += 8 + n
        elif block == 0x20:
            _need(data, block, at, 2)
            t += u(data, at, 2) * T_STATES // 1000
            at += 2
        elif block == 0x22:
            pass
        elif block in _SKIP_BLOCKS:
            hdr, off, size = _SKIP_BLOCKS[block]
            _need(data, block, at, hdr)
            total = hdr + u(data, at + off, size)
            _need(data, block, at, total)
            at += total
        else:
            raise TsxError(f"block {block:02X}h at {at - 1:X}h is not one that snapcas reads")
    return found
