#!/usr/bin/env python3
"""Run a game's restorer in openMSX and check the restore (docs/INTERNALS.md,
Check).

Usage: check.py <game> <machine> --dos <dir> [--options <text>]

<game> and <machine> are as for capture.py. <dir> holds the DOS system files:
NEXTOR.SYS and COMMAND2.COM, MSXDOS2.SYS and COMMAND2.COM, or MSXDOS.SYS and
COMMAND.COM. The report goes to check/report.txt in the game's work folder.

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

TIMEOUT = 600  # real seconds for one check


def read_facts(out):
    """build.txt's facts (INTERNALS.md, Check): the service flag, the patched
    ranges, and the tape service's part, moved part and C_POS's address, each
    as a Tcl list, empty when the image has none."""
    facts = {"service": "0", "patched": [], "part": "", "moved": "", "cpos": "0"}
    with open(os.path.join(out, "build.txt")) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, value = line.rstrip("\n").split(" ", 1)
                if key == "patched":
                    facts["patched"].append(value)
                else:
                    facts[key] = value
    return facts


def capture_reset(snap):
    """The seconds from the snapshot to the first reset that the capture's log
    holds in the 60 seconds after it, or "" (INTERNALS.md, Check, point 3)."""
    snapshot = None
    with open(os.path.join(snap, "log.txt")) as f:
        for line in f:
            time, _, text = line.partition(" ")
            if text.startswith("snapshot"):
                snapshot = float(time)
            elif snapshot is not None and text.startswith("the game reset the machine"):
                delay = float(time) - snapshot
                return f"{delay:.1f}" if delay < 60 else ""
    return ""


def settings(state, snap, image, report, check_dir, state_name, facts):
    """Tcl variables for check.tcl."""
    with open(image, "rb") as f:
        header = f.read(4096)
    tail = struct.unpack_from("<H", header, 52)[0]
    names = "af bc de hl af2 bc2 de2 hl2 ix iy sp".split()
    values = " ".join(f"{n.upper()} {int(state[n], 16)}" for n in names)
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
        "service": facts["service"],
        "regs": "{" + values + "}",
        "pc": str(int(state["pc"], 16)),
        "kv": "{" + " ".join(f"{k} {v}" for k, v in state.items()) + "}",
        "patched": "{" + " ".join(facts["patched"]) + "}",
        # The service's page 3 part, when build.py moved it from FCE1h.
        "p3": "{" + facts["moved"] + "}",
        "part": "{" + facts["part"] + "}",
        "cpos": facts["cpos"],
        "capreset": msx.tcl_word(capture_reset(snap)),
    }
    return "".join(f"set ::C({k}) {v}\n" for k, v in s.items())


def main():
    parser = argparse.ArgumentParser(description="Run a game's restorer in openMSX and check the restore.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    parser.add_argument("--options", default="", help="the restorer's options, such as /T1200, after the game's name")
    args = parser.parse_args()

    folder = gamefile.game_folder(args.game)
    try:
        game = gamefile.read_game(folder, args.machine)
        machine = msx.read_machine(msx.machine_path(args.machine))
        dos = sorted(glob.glob(os.path.join(args.dos, "*")))
        if not dos:
            raise OSError(f"{args.dos}: no DOS system files")
        out = gamefile.out_folder(args.machine, folder)
        snap = os.path.join(out, "snap")
        image = gamefile.image_path(args.machine, folder, game.name)
        state = build.read_state(snap)
        if not os.path.exists(image):
            raise OSError(f"{image}: no image; run build.py first")
        facts = read_facts(out)
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        print(f"check.py: {e}", file=sys.stderr)
        return 1

    check_dir = os.path.join(out, "check")
    shutil.rmtree(check_dir, ignore_errors=True)
    os.makedirs(check_dir)
    autoexec = os.path.join(check_dir, "AUTOEXEC.BAT")
    with open(autoexec, "w", newline="") as f:
        f.write(f"SNAPCAS {game.name} {args.options}".rstrip() + "\r\n")
    disk = os.path.join(check_dir, "disk.dsk")
    try:
        msx.make_disk(disk, dos + [os.path.join(ROOT, "bin", "SNAPCAS.COM"), image, autoexec], machine.disk_size)
    except RuntimeError as e:
        print(f"check.py: {e}", file=sys.stderr)
        return 2
    report = os.path.join(check_dir, "report.txt")
    state_name = f"snapcas-check-{os.getpid()}"
    script = (settings(state, snap, image, report, check_dir, state_name, facts)
              + msx.tcl("tcl/memory.tcl") + msx.tcl("tcl/check.tcl")
              + "\nboot {" + msx.boot_steps(machine) + "} "
              # On a machine that boots DOS from its own disk, the check's disk
              # is another drive, where AUTOEXEC.BAT runs SNAPCAS.
              + "{" + (msx.at_prompt(machine, f"{machine.dos[1]}:\rAUTOEXEC", "start_check")
                       if machine.dos else "start_check") + "}\n")
    try:
        msx.run([*machine.args, f"-{machine.disk}", os.path.abspath(disk)], script, timeout=TIMEOUT)
    except Exception as e:
        print(f"check.py: openMSX failed: {e}", file=sys.stderr)
        return 2
    # The savestates of point 2, from openMSX's savestate folder.
    home = msx.home()
    for path in glob.glob(os.path.join(home, "savestates", state_name + "-*.oms")):
        shutil.move(path, os.path.join(check_dir, os.path.basename(path)[len(state_name) + 1:]))
    if not os.path.exists(report):
        print(f"check.py: openMSX stopped before the report; see {check_dir}", file=sys.stderr)
        return 2
    with open(report) as f:
        text = f.read()
    print(text, end="")
    failed = any(f"point {n}: fail" in text for n in (2, 3, 4))
    return 0 if text.startswith("point 1: pass") and not failed else 3


if __name__ == "__main__":
    sys.exit(main())
