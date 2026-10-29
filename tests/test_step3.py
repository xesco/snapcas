"""Step 3 (docs/PLAN.md): the image, from the snapshots of step 2, checked
against the design's tables (DESIGN.md, Formats)."""
import os
import struct
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402
import test_step2  # noqa: E402

WORK = os.path.join(ROOT, "out", "test", "step3")

# game: (CAS file, machine), all single loads.
GAMES = {
    "freddy": ("FREDDY.CAS", "advanced/phc28s"),
    "fernando": ("FERNANDO.CAS", "advanced/phc28s"),
    "caldero": ("CALDERO.CAS", "advanced/phc28s"),
    "freddy8250": ("FREDDY.CAS", "basic/nms8250"),
}


def run_build(game, machine, *extra):
    return subprocess.run(
        [sys.executable, "-I", os.path.join(ROOT, "tools", "build.py"),
         os.path.join(WORK, "games", game), machine, "--cas", test_step2.CAS_DIR, *extra],
        capture_output=True, text=True)


class Crc(unittest.TestCase):
    def test_check_value(self):
        # The check value of CRC-16/CCITT-FALSE.
        self.assertEqual(build.crc16(b"123456789"), 0x29B1)


class PortWrites(unittest.TestCase):
    def state(self, **values):
        s = {f"psg{r}": "00" for r in range(16)}
        s.update({f"vdp{r}": "00" for r in list(range(24)) + list(range(32, 46))})
        s.update({f"pal{c}": "0000" for c in range(16)})
        s.update(psgsel="0E", ppic="50", vramptr="00000", vramwrite="1")
        s.update(values)
        return s

    def test_psg_register_7_and_the_selected_register(self):
        w = build.port_writes(self.state(psg7="3F", psgsel="0E"), False)
        self.assertEqual(w[14:16], [(0xA0, 7), (0xA1, 0xBF)])
        self.assertEqual(w[32], (0xA0, 0x0E))
        self.assertEqual(w[33], (0xAA, 0x50))

    def test_write_setup(self):
        w = build.port_writes(self.state(vramptr="01234", vramwrite="1"), True)
        self.assertEqual(w[-2:], [(0x99, 0x34), (0x99, 0x52)])

    def test_read_setup_writes_the_pointer_minus_1(self):
        w = build.port_writes(self.state(vramptr="01234", vramwrite="0"), True)
        self.assertEqual(w[-2:], [(0x99, 0x33), (0x99, 0x12)])

    def test_read_setup_borrows_from_register_14(self):
        w = build.port_writes(self.state(vramptr="08000", vramwrite="0"), True)
        self.assertEqual(w[-4:], [(0x99, 1), (0x99, 0x8E), (0x99, 0xFF), (0x99, 0x3F)])

    def test_v9938_order(self):
        w = build.port_writes(self.state(pal1="7005"), True)
        self.assertEqual(w[34:36], [(0x99, 0), (0x99, 0x90)])
        self.assertEqual(w[38:40], [(0x9A, 0x70), (0x9A, 0x05)])
        self.assertEqual(w[68:70], [(0x99, 32), (0x99, 0x91)])
        self.assertEqual([p for p, _ in w[70:84]], [0x9B] * 14)
        self.assertEqual(len(w), 34 + 2 + 32 + 2 + 14 + 48 + 2)


@unittest.skipUnless(os.path.isdir(test_step2.CAS_DIR), "CAS_DIR names no folder of CAS files")
class Images(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = {}
        for game, (cas, machine) in GAMES.items():
            games = os.path.join(WORK, "games", game)
            os.makedirs(games, exist_ok=True)
            with open(os.path.join(games, "game.txt"), "w") as f:
                f.write(f"cas {cas}\n")
            snap = os.path.join(ROOT, "out", machine, game, "snap")
            if not os.path.exists(os.path.join(snap, "state.txt")):
                subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "capture.py"),
                                games, machine, "--cas", test_step2.CAS_DIR], check=True,
                               capture_output=True)
            result = run_build(game, machine)
            if result.returncode != 0:
                raise AssertionError(f"{game}: {result.stderr}")
            name = build.gamefile.default_name(game)
            with open(os.path.join(ROOT, "out", machine, game, f"{name}.SNP"), "rb") as f:
                cls.images[game] = (f.read(), build.read_state(snap), snap)

    def header(self, image):
        h = image[:4096]
        rom, subrom, records, writes = struct.unpack_from("<HHBB", h, 8)
        table = [h[64 + 4 * n:68 + 4 * n] for n in range(records)]
        start = 64 + 4 * records
        ports = [tuple(h[start + 2 * n:start + 2 * n + 2]) for n in range(writes)]
        return h, rom, subrom, table, ports

    def test_mark_crcs_and_size(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                h, rom, subrom, table, _ = self.header(image)
                self.assertEqual(h[:8], b"SNAPCAS2")
                with open(os.path.join(snap, "rom.bin"), "rb") as f:
                    self.assertEqual(rom, build.crc16(f.read()))
                if os.path.exists(os.path.join(snap, "subrom.bin")):
                    with open(os.path.join(snap, "subrom.bin"), "rb") as f:
                        self.assertEqual(subrom, build.crc16(f.read()))
                else:
                    self.assertEqual(subrom, 0)
                full = sum(1 for r in table if r[0] != build.VRAM_ZEROS)
                self.assertEqual(len(image), 4096 + 16384 * full)

    def test_registers(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                h = image[:4096]
                names = "af bc de hl af2 bc2 de2 hl2 ix iy sp pc".split()
                self.assertEqual(list(struct.unpack_from("<12H", h, 16)),
                                 [int(state[n], 16) for n in names])
                self.assertEqual(h[40], int(state["i"], 16))
                self.assertEqual(h[41], int(state["im"], 16))
                self.assertEqual(h[42], int(state["iff"], 16) & 1)
                self.assertEqual(h[43], int(state["a8"], 16))

    def test_records(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                _, _, _, table, _ = self.header(image)
                ram = [r for r in table if r[0] in (build.RAM_IN_MAPPER, build.RAM)]
                vram = [r for r in table if r[0] in (build.VRAM, build.VRAM_ZEROS)]
                files = os.listdir(os.path.join(snap, "ram"))
                self.assertTrue(ram)
                self.assertLessEqual(len(ram), len(files))
                self.assertEqual(sorted(r[1] for r in vram),
                                 list(range(os.path.getsize(os.path.join(snap, "vram.bin")) // 16384)))

    def test_port_writes_start_with_the_psg_and_end_with_the_pointer(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                _, _, _, _, ports = self.header(image)
                self.assertEqual([p for p, _ in ports[:32]], [0xA0, 0xA1] * 16)
                self.assertEqual(ports[33], (0xAA, int(state["ppic"], 16)))
                if state["vramwrite"] == "1":
                    self.assertTrue(ports[-1][1] & 0x40)

    def test_tail(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                h, _, _, table, _ = self.header(image)
                tail = struct.unpack_from("<H", h, 52)[0]
                sp, pc, af = (int(state[n], 16) for n in ("sp", "pc", "af"))
                self.assertEqual(tail, sp - 26)
                page = tail >> 14
                ps, ss = build.selected(state, page)
                slot = ps if ss is None else 0x80 | (ss << 2) | ps
                n = [i for i, r in enumerate(table) if r[0] in (1, 2) and r[1] == slot and r[2] == page][0]
                data = image[4096 + 16384 * n:4096 + 16384 * (n + 1)]
                code = data[tail & 0x3FFF:(tail & 0x3FFF) + 26]
                ei = 0xFB if int(state["iff"], 16) & 1 else 0x00
                expected = (bytes([0x3E, 0, 0xD3, 0, 0x3E, 0, 0xD3, 0xA8, 0x3E, 0, 0, 0, 0, 0x31])
                            + struct.pack("<H", tail + 24) + bytes([0xF1, 0x31])
                            + struct.pack("<H", sp) + bytes([ei, 0xC3])
                            + struct.pack("<H", pc) + struct.pack("<H", af))
                self.assertEqual(code, expected)

    def test_a_wrong_service_version_is_refused(self):
        with open(os.path.join(ROOT, "bin", "SERVICE.BIN"), "rb") as f:
            data = bytearray(f.read())
        data[0] = build.SERVICE_VERSION + 1
        wrong = os.path.join(WORK, "SERVICE.BIN")
        with open(wrong, "wb") as f:
            f.write(data)
        result = run_build("freddy", GAMES["freddy"][1], "--service", wrong)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"version {build.SERVICE_VERSION + 1}, expected {build.SERVICE_VERSION}",
                      result.stderr)


if __name__ == "__main__":
    unittest.main()
