#!/usr/bin/env python3
"""Run a game's restorer in openMSX and check the restore (docs/DESIGN.md,
Check).

Usage: check.py <game> <machine> --dos <dir>

<game> and <machine> are as for capture.py. <dir> holds the DOS system files:
NEXTOR.SYS and COMMAND2.COM, MSXDOS2.SYS and COMMAND2.COM, or MSXDOS.SYS and
COMMAND.COM. The report goes to out/<machine>/<game>/check/report.txt.

Exit status: 0 when the check passes, 1 for an error in the input files, 2
when openMSX fails, 3 when the check fails.
"""
import argparse
import glob
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import scan  # noqa: E402

TIMEOUT = 600  # real seconds for one check


def selected_name(state, page):
    """The primary slot and subslot, as ram/ file names write them, that the
    snapshot selects in a page."""
    ps, ss = build.selected(state, page)
    return ps, "x" if ss is None else ss


def patched_bytes(state, snap, patches, page):
    """The RAM pages' bytes that the patch lines and the scan change, as
    ps-ss-page, first and last offset. The scan's patches point to the entries
    at page's E1h, and page is 0 without a part in page 3, where the scan
    patches nothing."""
    ranges = ["{}-{}-{} {} {}".format(*selected_name(state, p.page), p.page, p.offset, p.offset + len(p.old) - 1)
              for p in patches if p.page not in ("side1", "side2")]
    if state["service"] == "1" and page:
        for name in sorted(os.listdir(os.path.join(snap, "ram"))):
            with open(os.path.join(snap, "ram", name), "rb") as f:
                findings = scan.find(f.read(), page)
            ps, ss, ram_page, _ = name[:-4].split("-")
            ranges += [f"{ps}-{ss}-{ram_page} {f.offset} {f.offset + len(f.old) - 1}"
                       for f in findings if f.new is not None]
    return ranges


def settings(state, snap, image, report, check_dir, state_name, patches):
    """Tcl variables for check.tcl."""
    with open(image, "rb") as f:
        header = f.read(4096)
    tail = struct.unpack_from("<H", header, 52)[0]
    names = "af bc de hl af2 bc2 de2 hl2 ix iy sp".split()
    values = " ".join(f"{n.upper()} {int(state[n], 16)}" for n in names)
    keep = {k: v for k, v in state.items()}
    with open(os.path.join(ROOT, "bin", "SNAPCAS.COM"), "rb") as f:
        com = f.read(3)
    s = {
        "com": "{" + " ".join(str(b) for b in com) + "}",
        "report": msx.tcl_word(report),
        "snap": msx.tcl_word(snap),
        "dir": msx.tcl_word(check_dir),
        "state": state_name,
        "tail": str(tail),
        "a8": str(header[43]),
        "service": "1" if any(header[64 + 4 * n] == build.SERVICE_SEGMENT for n in range(header[12])) else "0",
        "regs": "{" + values + "}",
        "pc": str(int(state["pc"], 16)),
        "kv": "{" + " ".join(f"{k} {v}" for k, v in keep.items()) + "}",
        "patched": "{" + " ".join(patched_bytes(state, snap, patches, header[15])) + "}",
        # The service's page 3 part, when build.py moved it from FCE1h.
        "p3": "{}" if header[15] in (0, build.DEFAULT_PAGE) else
              f"{{{header[15] * 256 + 0xE1} {(header[15] + 1) * 256 + 0x88}}}",
    }
    return "".join(f"set ::C({k}) {v}\n" for k, v in s.items())


def main():
    parser = argparse.ArgumentParser(description="Run a game's restorer in openMSX and check the restore.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    args = parser.parse_args()

    folder = (os.path.abspath(args.game) if os.sep in args.game or os.path.isdir(args.game)
              else os.path.join(ROOT, "games", args.game))
    try:
        game = gamefile.read_game(folder)
        machine = msx.read_machine(os.path.join(ROOT, "machines", args.machine + ".txt"))
        dos = sorted(glob.glob(os.path.join(args.dos, "*")))
        if not dos:
            raise OSError(f"{args.dos}: no DOS system files")
        name = os.path.basename(os.path.normpath(folder))
        out = os.path.join(ROOT, "out", args.machine, name)
        snap = os.path.join(out, "snap")
        image = os.path.join(out, f"{game.name}.SNP")
        state = build.read_state(snap)
        if not os.path.exists(image):
            raise OSError(f"{image}: no image; run build.py first")
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        print(f"check.py: {e}", file=sys.stderr)
        return 1

    check_dir = os.path.join(out, "check")
    shutil.rmtree(check_dir, ignore_errors=True)
    os.makedirs(check_dir)
    autoexec = os.path.join(check_dir, "AUTOEXEC.BAT")
    with open(autoexec, "w", newline="") as f:
        f.write(f"SNAPCAS {game.name}\r\n")
    disk = os.path.join(check_dir, "disk.dsk")
    try:
        msx.make_disk(disk, dos + [os.path.join(ROOT, "bin", "SNAPCAS.COM"), image, autoexec])
    except RuntimeError as e:
        print(f"check.py: {e}", file=sys.stderr)
        return 2
    report = os.path.join(check_dir, "report.txt")
    state_name = f"snapcas-check-{os.getpid()}"
    with open(os.path.join(HERE, "capture.tcl")) as f:
        procedures = f.read()
    with open(os.path.join(HERE, "check.tcl")) as f:
        check = f.read()
    script = (settings(state, snap, image, report, check_dir, state_name, game.patches)
              + procedures + check
              + "\nboot {" + msx.boot_steps(machine) + "} start_check\n")
    try:
        msx.run([*machine.args, f"-{machine.disk}", os.path.abspath(disk)], script, timeout=TIMEOUT)
    except Exception as e:
        print(f"check.py: openMSX failed: {e}", file=sys.stderr)
        return 2
    # The savestates of point 2, from openMSX's savestate folder.
    home = os.environ.get("OPENMSX_HOME", os.path.join(os.path.expanduser("~"), ".openMSX"))
    for path in glob.glob(os.path.join(home, "savestates", state_name + "-*.oms")):
        shutil.move(path, os.path.join(check_dir, os.path.basename(path)[len(state_name) + 1:]))
    if not os.path.exists(report):
        print(f"check.py: openMSX stopped before the report; see {check_dir}", file=sys.stderr)
        return 2
    with open(report) as f:
        text = f.read()
    print(text, end="")
    return 0 if text.startswith("point 1: pass") else 3


if __name__ == "__main__":
    sys.exit(main())
