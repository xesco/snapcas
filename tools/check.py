#!/usr/bin/env python3
"""Run a game's restorer in openMSX and check the restore (docs/INTERNALS.md,
Check).

Usage: check.py <game> <machine> --dos <dir>

<game> and <machine> are as for capture.py. <dir> holds the DOS system files:
NEXTOR.SYS and COMMAND2.COM, MSXDOS2.SYS and COMMAND2.COM, or MSXDOS.SYS and
COMMAND.COM. The report goes to check/report.txt in the game's work folder.

Exit status: 0 when the check passes, 1 for an error in the command line or
the input files, 2 when openMSX fails, 3 when the check fails.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamefile  # noqa: E402
import msx  # noqa: E402
from snapshot import Snapshot  # noqa: E402

TIMEOUT = 600  # real seconds for one check
COM = os.path.join(ROOT, "bin", "SNAPCAS.COM")
# The restorer's symbols, which make all writes: the check works without them.
SYMBOLS = os.path.join(ROOT, "out", "snapcas.sym")
# The seconds that the restored game runs in the check.
SECONDS = 60


def read_facts(out):
    """build.txt's facts (INTERNALS.md, Check), under their names: the service
    flag, the tail's address and fields, the area that the service's part of
    page 3 takes by default, the patched ranges, and the tape service's part,
    moved part, tape positions' addresses and the addresses of its jumps at
    the tape's end, each as a Tcl list, empty when the image has none."""
    facts = {"service": "0", "tail": "", "free": "", "patched": [], "part": "", "moved": "", "cpos": "",
             "ended": ""}
    with open(os.path.join(out, "build.txt")) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, value = line.rstrip("\n").split(" ", 1)
                if key == "patched":
                    facts["patched"].append(value)
                else:
                    facts[key] = value
    facts["patched"] = " ".join(facts["patched"])
    return facts


def capture_reset(snapshot):
    """The seconds from the snapshot to the first reset that the capture's log
    holds after it, or "" (INTERNALS.md, Check, point 3). The capture goes on
    for 29 seconds after the moment that it saves for the snapshot, so the log
    holds the resets of those seconds. A snapshot at a TAPION call's entry is
    earlier than that moment, so a reset can come later after it: one that
    comes after the check's seconds does not count."""
    taken = None
    with open(snapshot.path("log.txt")) as f:
        for line in f:
            time, _, text = line.partition(" ")
            if text.startswith("snapshot"):
                taken = float(time)
            elif taken is not None and text.startswith("the game reset the machine"):
                delay = float(time) - taken
                return f"{delay:.1f}" if delay < SECONDS else ""
    return ""


def stop_address(com, symbols):
    """The address of the restorer's stop_message, where it prints the message
    that refuses an image, and the 3 bytes there in SNAPCAS.COM's bytes, as a
    Tcl list. Empty without the symbols, or when they are another assembly's
    than SNAPCAS.COM: stop_message starts with a call of print."""
    found = {}
    try:
        with open(symbols) as f:
            for line in f:
                label, _, value = line.partition(": EQU ")
                if label in ("stop_message", "print"):
                    found[label] = int(value, 16)
    except (OSError, ValueError):
        return ""
    if len(found) < 2:
        return ""
    offset = found["stop_message"] - 0x100
    code = bytes([0xCD]) + struct.pack("<H", found["print"])
    if offset < 0 or com[offset:offset + 3] != code:
        return ""
    return f"{found['stop_message']} " + " ".join(str(b) for b in code)


def verdict(report):
    """The exit status for a report's text: 0 when all four points pass, 3
    when one fails, and 2 for a report that openMSX left before its end.
    check.tcl writes point 1 at the restore and points 2 to 4 together, 60
    emulated seconds later, so a report that stops after a passed point 1 is
    one that openMSX left, unless it ends with a point that an error of
    check.tcl failed, which its "check:" line shows."""
    lines = report.splitlines()
    if all(f"point {n}: pass" in lines for n in (1, 2, 3, 4)):
        return 0
    ended = any(line.startswith(("point 4:", "  check: ")) for line in lines)
    return 2 if "point 1: pass" in lines and not ended else 3


# The two results of a point in the report.
RESULTS = ("pass", "fail")


def points(report):
    """A report's points, in its order, as [(number, whether it passes, the
    lines of what failed it)]. The lines keep their indent. A line before the
    first point is in a first entry whose number is None."""
    found = []
    for line in report.splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "point" and words[1] in ("1:", "2:", "3:", "4:") and words[2] in RESULTS:
            found.append((int(words[1][:-1]), words[2] == "pass", []))
        else:
            if not found:
                found.append((None, False, []))
            found[-1][2].append(line)
    return found


def settings(snapshot, report, name, state_name, facts):
    """Tcl variables for check.tcl: its own, the names and values of the
    snapshot's state as kv, and build.txt's facts under their names."""
    with open(COM, "rb") as f:
        com = f.read()
    s = {
        "report": msx.tcl_word(report),
        "snap": msx.tcl_word(snapshot.folder),
        "pages": str(len(snapshot.ram_names)),
        "kv": "{" + " ".join(f"{k} {v}" for k, v in snapshot.state.items()) + "}",
        "capreset": msx.tcl_word(capture_reset(snapshot)),
        "state": state_name,
        "name": msx.tcl_word(name),
        "com": msx.tcl_bytes(com[:3]),
        "stop": "{" + stop_address(com, SYMBOLS) + "}",
        **{key: "{" + value + "}" for key, value in facts.items()},
    }
    return "".join(f"set ::C({k}) {v}\n" for k, v in s.items())


def check(game_arg, machine_name, dos_dir):
    """Runs the restorer of a game's image in openMSX on a machine, as
    check.py's arguments name them, with the DOS system files of dos_dir.
    Returns the verdict, 0 when the check passes and 3 when it fails, and the
    report's text. Raises msx.Failure for an error in the input files and for a
    run without a whole report."""
    try:
        folder = gamefile.game_folder(game_arg)
        game = gamefile.read_game(folder, machine_name)
        machine = msx.read_machine(msx.machine_path(machine_name))
        dos = msx.dos_files(dos_dir)
        out = gamefile.out_folder(machine_name, folder)
        image = gamefile.image_path(machine_name, folder, game.name)
        snapshot = Snapshot(os.path.join(out, "snap")).load()
        if not os.path.exists(image):
            raise OSError(f"{image}: no image; run build.py first")
        facts = read_facts(out)
        check_dir = os.path.join(out, "check")
        report = os.path.join(check_dir, "report.txt")
        # The savestates' names hold the process ID, so that checks can run
        # side by side.
        state_name = f"snapcas-check-{os.getpid()}"
        if not facts["tail"]:
            raise OSError(f"{out}/build.txt: no tail line; run build.py again")
        script = (settings(snapshot, report, game.name, state_name, facts)
                  + msx.tcl("tcl/memory.tcl") + msx.tcl("tcl/check.tcl")
                  + "\nsafe {boot {" + msx.boot_steps(machine) + "} "
                  # On a machine that boots DOS from its own disk, the check's disk
                  # is another drive, where AUTOEXEC.BAT runs SNAPCAS.
                  + "{" + (msx.at_prompt(machine, f"{machine.dos[1]}:\rAUTOEXEC", "start_check")
                           if machine.dos else "start_check") + "}}\n")
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        raise msx.Failure(1, f"check.py: {e}")

    shutil.rmtree(check_dir, ignore_errors=True)
    os.makedirs(check_dir)
    autoexec = os.path.join(check_dir, "AUTOEXEC.BAT")
    with open(autoexec, "w", newline="") as f:
        f.write(f"SNAPCAS {game.name}\r\n")
    disk = os.path.join(check_dir, "disk.dsk")
    try:
        msx.make_disk(disk, dos + [COM, image, autoexec], machine.disk_size)
    except msx.DiskError as e:
        raise msx.Failure(2, f"check.py: {e}", broke=e.broke)
    # An earlier run with the same process ID can have left savestates.
    msx.remove_savestates(state_name)
    try:
        stderr = msx.run([*machine.args, f"-{machine.disk}", os.path.abspath(disk)], script, timeout=TIMEOUT)
        # The savestates of point 2, from openMSX's savestate folder.
        for path in msx.savestates(state_name):
            shutil.move(path, os.path.join(check_dir, os.path.basename(path)[len(state_name) + 1:]))
    except Exception as e:
        raise msx.Failure(2, f"check.py: openMSX failed: {e}", broke=True)
    finally:
        # Those that a stopped openMSX leaves.
        msx.remove_savestates(state_name)
    if not os.path.exists(report):
        raise msx.Failure(2, f"check.py: openMSX stopped before the report; see {check_dir}{msx.last_output(stderr)}",
                          broke=True)
    with open(report) as f:
        text = f.read()
    status = verdict(text)
    if status == 2:
        raise msx.Failure(2, "check.py: openMSX stopped before the report's end; see "
                          f"{check_dir}{msx.last_output(stderr)}", broke=True, output=text)
    return status, text


def main():
    parser = msx.Parser(description="Run a game's restorer in openMSX and check the restore.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    args = parser.parse_args()
    try:
        status, text = check(args.game, args.machine, args.dos)
    except msx.Failure as e:
        return e.show()
    print(text, end="")
    return status


if __name__ == "__main__":
    sys.exit(main())
