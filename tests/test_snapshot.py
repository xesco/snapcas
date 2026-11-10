"""A snapshot's folder as tools/snapshot.py reads it (docs/FORMATS.md,
Snapshot files), on the snapshot that support.snapshot writes. Pure tier."""
import os
import unittest

import support
import build
import gamefile
from snapshot import RamName, Snapshot, SnapshotError


class Fixture(unittest.TestCase):
    def snapshot(self, **options):
        """A snapshot of support.snapshot, as snapshot.py reads it."""
        return Snapshot(support.snapshot(support.temp(self), **options))


class SelectedPage(Fixture):
    def test_a_mapper_register_selects_its_value_modulo_the_mappers_size(self):
        # A game writes 81h to register FEh of a mapper of 32 segments, which
        # selects segment 1, and the capture names the page's file after it.
        snapshot = self.snapshot(ram={"3-x-2-1": bytes(build.PAGE)}, a8="FF", fc="03", fd="02", fe="81", ff="00",
                                 **{"mapper3-x": "20"})
        self.assertIs(snapshot.selected_ram(2), snapshot.ram_pages[0])
        self.assertIsNone(snapshot.selected_ram(1))

    def test_a_snapshot_without_the_sizes_selects_by_the_registers_value(self):
        snapshot = self.snapshot(ram={"3-x-2-1": bytes(build.PAGE)}, a8="FF", fc="3", fd="2", fe="1", ff="0")
        self.assertNotIn("mapper3-x", snapshot.state)
        self.assertIs(snapshot.selected_ram(2), snapshot.ram_pages[0])

    def test_the_fixtures_pages_are_the_ones_that_its_registers_select(self):
        for options, files in (({}, ["3-x-1-2.bin", "3-x-2-1.bin", "3-x-3-0.bin"]),
                               ({"mapper": False}, ["3-x-1-x.bin", "3-x-2-x.bin", "3-x-3-x.bin"])):
            with self.subTest(options=options):
                snapshot = self.snapshot(**options)
                self.assertEqual([snapshot.selected_ram(page).name.file for page in (1, 2, 3)], files)
                # Page 0 selects the ROM, in slot 0.
                self.assertEqual((snapshot.selected_slot(0), snapshot.selected_ram(0)), ((0, None), None))


class SnapshotFolder(Fixture):
    def test_a_ram_files_name_reads_and_prints_the_same(self):
        for file, values in (("3-x-2-1.bin", (3, None, 2, 1)), ("0-2-3-x.bin", (0, 2, 3, None)),
                             ("1-x-0-x.bin", (1, None, 0, None)), ("3-3-1-255.bin", (3, 3, 1, 255))):
            with self.subTest(file=file):
                name = RamName.parse(file)
                self.assertEqual(tuple(name), values)
                self.assertEqual(name.file, file)
                self.assertEqual(RamName.parse(RamName(*values).file), name)

    def test_a_ram_files_name_gives_what_the_build_and_the_check_name(self):
        name = RamName.parse("0-2-3-x.bin")
        self.assertEqual((name.stem, name.cpu_page, name.slot_id), ("0-2-3-x", "0-2-3", 0x88))
        self.assertEqual(RamName.parse("3-x-2-1.bin").slot_id, 3)
        # A mapper's segment is one RAM page in whatever page it is, and a
        # page outside a mapper is its own.
        self.assertEqual(RamName.parse("3-x-2-5.bin").key, RamName.parse("3-x-3-5.bin").key)
        self.assertNotEqual(RamName.parse("3-x-2-x.bin").key, RamName.parse("3-x-3-x.bin").key)

    def test_a_segment_in_two_pages_is_one_ram_page_with_two_names(self):
        read = self.snapshot(shared=True)
        self.assertEqual([page.name.file for page in read.ram_pages], ["3-x-1-2.bin", "3-x-2-5.bin"])
        self.assertEqual([name.file for name in read.ram_names], ["3-x-1-2.bin", "3-x-2-5.bin", "3-x-3-5.bin"])
        self.assertEqual([name.file for name in read.names_of(read.ram_pages[1])], ["3-x-2-5.bin", "3-x-3-5.bin"])
        self.assertIs(read.selected_ram(3), read.ram_pages[1])
        self.assertIs(read.selected_ram(2), read.ram_pages[1])
        self.assertEqual(read.selected_slot(3), (3, None))

    def test_the_state_gives_numbers_and_the_selected_slots(self):
        read = self.snapshot(ram={}, a8="D4", sub1="E4", sp="F000", **{"mapper1-2": "20"})
        self.assertEqual((read.num("sp"), read.num("sub0"), read.state["sub0"]), (0xF000, 0, "-"))
        # Page 1 is in slot 1, which is expanded, and its field of the
        # subslot register, E4h, is 1. Page 0 is in slot 0, which is not.
        self.assertEqual((read.selected_slot(1), read.selected_slot(0)), ((1, 1), (0, None)))
        self.assertEqual((read.mapper_size((1, 2)), read.mapper_size((3, None))), (0x20, None))

    def test_a_ram_file_of_another_size_stops_the_read(self):
        with self.assertRaisesRegex(SnapshotError, "ram/3-x-3-0.bin: not 16 KB"):
            self.snapshot(ram={"3-x-3-0": bytes(100)}).ram_pages

    def test_a_folder_without_a_state_is_no_snapshot(self):
        with self.assertRaises(OSError):
            Snapshot(support.temp(self)).load()
        read = self.snapshot()
        self.assertIs(read.load(), read)

    def test_the_slot_map_is_read_for_each_page(self):
        read = self.snapshot()
        self.assertEqual(read.slots, {page: (set(), -1) for page in range(4)})
        with open(read.path("slots.txt"), "w") as f:
            f.write("# The PHC-28S's.\npage 0 empty 3 with 2\npage 2 empty 0,3 with 2\n")
        self.assertEqual(Snapshot(read.folder).slots, {0: ({3}, 2), 2: ({0, 3}, 2)})
        os.remove(read.path("slots.txt"))
        self.assertIsNone(Snapshot(read.folder).slots)

    def test_the_captures_patches_are_read_as_the_capture_writes_them(self):
        read = self.snapshot(ram={})
        self.assertEqual((read.capture_patches(), read.new_patches(), read.error()), ([], None, None))
        lines = ["patch side1:24E 3E FC D3 A8 > 3E 14 D3 A8", "patch side2:10 00 > 01"]
        with open(read.path("newpatch.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        read.write_patches(read.new_patches())
        patches = read.capture_patches()
        self.assertEqual([(p.side, p.page, p.offset, p.old, p.new, p.line) for p in patches],
                         [(1, None, 0x24E, bytes.fromhex("3EFCD3A8"), bytes.fromhex("3E14D3A8"), lines[0]),
                          (2, None, 0x10, b"\0", b"\1", lines[1])])
        data = bytearray(0x24E) + bytearray.fromhex("3EFCD3A8")
        patches[0].apply(data)
        self.assertEqual(data[0x24E:], bytes.fromhex("3E14D3A8"))
        with self.assertRaisesRegex(gamefile.GameFileError,
                                    "patches.txt: the bytes at side1:24E are not the patch's old bytes"):
            patches[0].apply(data)

    def test_a_captures_error_is_its_files_text(self):
        read = self.snapshot()
        with open(read.path("error.txt"), "w") as f:
            f.write("capture: the CPU is halted with no interrupt, at 1234\n")
        self.assertEqual(read.error(), "capture: the CPU is halted with no interrupt, at 1234")


if __name__ == "__main__":
    unittest.main()
