"""The reader of TSX files (docs/FORMATS.md, TSX data, and docs/INTERNALS.md,
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


def read(data):
    """The file's blocks that hold bytes or signal, as the fields of
    tape.Block: standard, the bytes, their offset in the file, and the
    player's seconds at the block's start and end. A block that the file's
    end cuts stops the reader, as a file cut in a download has."""
    if data[:8] != SIGNATURE:
        raise TsxError("not a TSX file: no ZXTape! signature")
    at, t, found = 10, 0, []

    def need(n):
        if at + n > len(data):
            raise TsxError(f"block {block:02X}h at {at - 1:X}h goes past the file's end")

    def add(is_standard, start, end, length):
        nonlocal t
        found.append((is_standard, bytes(data[start:end]), start, t / T_STATES, (t + length) / T_STATES))
        t += length

    while at < len(data):
        block, at = data[at], at + 1
        if block == 0x10:
            need(4)
            pause, n = u(data, at, 2), u(data, at + 2, 2)
            need(4 + n)
            body = data[at + 4:at + 4 + n]
            pilots = 8063 if body and body[0] < 128 else 3223
            add(False, at + 4, at + 4 + n, pilots * 2168 + 667 + 735 + bits_time(body, 855, 1710))
            t += pause * T_STATES // 1000
            at += 4 + n
        elif block == 0x11:
            need(18)
            pilot, sync1, sync2, zero, one, pilots = (u(data, at + 2 * k, 2) for k in range(6))
            used, pause, n = data[at + 12], u(data, at + 13, 2), u(data, at + 15, 3)
            need(18 + n)
            if used > 8:
                raise TsxError(f"block 11h at {at - 1:X}h uses {used} bits of its last byte")
            body = data[at + 18:at + 18 + n]
            add(False, at + 18, at + 18 + n, pilots * pilot + sync1 + sync2 + bits_time(body, zero, one, used=used))
            t += pause * T_STATES // 1000
            at += 18 + n
        elif block == 0x12:
            need(4)
            t += u(data, at, 2) * u(data, at + 2, 2)
            at += 4
        elif block == 0x13:
            need(1)
            n = data[at]
            need(1 + 2 * n)
            t += sum(u(data, at + 1 + 2 * k, 2) for k in range(n))
            at += 1 + 2 * n
        elif block == 0x15:
            need(8)
            sample, pause, used, n = u(data, at, 2), u(data, at + 2, 2), data[at + 4], u(data, at + 5, 3)
            need(8 + n)
            # A recording of the signal, with no bytes to read or patch.
            add(False, at + 8, at + 8, sample * (8 * max(n - 1, 0) + used))
            t += pause * T_STATES // 1000
            at += 8 + n
        elif block == 0x20:
            need(2)
            t += u(data, at, 2) * T_STATES // 1000
            at += 2
        elif block in (0x21, 0x30):
            need(1)
            need(1 + data[at])
            at += 1 + data[at]
        elif block == 0x22:
            pass
        elif block == 0x32:
            need(2)
            need(2 + u(data, at, 2))
            at += 2 + u(data, at, 2)
        elif block == 0x35:
            need(20)
            need(20 + u(data, at + 16, 4))
            at += 20 + u(data, at + 16, 4)
        elif block == 0x4B:
            need(4)
            n = u(data, at, 4)
            need(4 + n)
            if n < 12:
                raise TsxError(f"block 4Bh at {at - 1:X}h is shorter than its 12 bytes of settings")
            body = data[at:at + 4 + n]
            add(standard(body), at + 16, at + 4 + n, kcs_time(body))
            t += u(body, 4, 2) * T_STATES // 1000
            at += 4 + n
        else:
            raise TsxError(f"block {block:02X}h at {at - 1:X}h is not one that snapcas reads")
    return found
