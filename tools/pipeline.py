#!/usr/bin/env python3
"""The steps that make a game's image on a machine (docs/DESIGN.md, Files and
commands): the capture, the build and the check, the trials of the machine's
capture variants, and the result of them all. snapcas.py snap prints from it,
and games.py runs it for each game file.

Usage: pipeline.py <game> <machine> --dos <dir>

<game> and <machine> are as for capture.py, and <dir> as for check.py. As a
program, it makes and checks one game's image, without the capture variants'
trials, and prints the result as one line of JSON. games.py starts it once for
each game file, so that each game has a process of its own: the names of its
savestates hold its process ID, Ctrl-C stops it with its openMSX, and a step
that ends in a Python error takes only its own game with it.

The steps are functions of capture.py, build.py and check.py, which raise
msx.Failure with the exit status that the tool gives as a program, its error,
and whether the run broke. So a result is made of what a step returns, and not
read from what it prints.

Exit status: 0 when the result is printed, whatever it is, 1 for an error in
the command line, 130 when Ctrl-C stops the steps.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
import capture  # noqa: E402
import check  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402

# The message of a result whose check passes: the first line of its report.
PASS = "point 1: pass"

# How a step ended: its name, capture, build or check, its exit status, 0 when
# it passes, its error, or "", whether the run broke, so that the error says
# nothing of the game, and its output: for the build, what the image holds,
# and for the check, the report's text.
Step = collections.namedtuple("Step", "name status error broke output")


class Result(collections.namedtuple("Result", "step status message transient variant image")):
    """How the steps of one game on one machine ended:

    step       the step that failed, capture, build or check, or None
    status     that step's exit status, or 0
    message    one line: the failed step's error, the failed point of the
               check with its first line, PASS when the check passes, or ""
               when the steps pass without a check
    transient  whether the run broke, so that the result says nothing of the
               game: openMSX failed, stopped before its result or timed out,
               or the steps ended in a Python error or by a signal
    variant    the capture variant whose trial passed, or None
    image      the image's path in images/, where a pass moves it, or None:
               for a result that fails, and for a game folder outside games/
               and custom/, whose image stays in its work folder
    """

    @property
    def passed(self):
        """Whether every step passed. With the check, that is check.py's
        rule: all four points pass (check.verdict)."""
        return self.status == 0


def tapes_folder(game):
    """The folder of the tapes of the game in a folder: a custom game's own
    folder, or downloads/."""
    return game if gamefile.is_custom(game) else gamefile.DOWNLOADS


def run_step(name, tool, *args):
    """Runs a step's tool, which returns the step's exit status and its
    output, and returns the Step."""
    try:
        status, output = tool(*args)
    except msx.Failure as e:
        return Step(name, e.status, e.error, e.broke, e.output)
    return Step(name, status, "", False, output)


def capture_step(game, machine, variant):
    capture.capture(game, machine, tapes_folder(game), variant)
    return 0, ""


def build_step(game, machine, variant):
    _, _, holds = build.write_image(game, machine, tapes_folder(game), variant=variant)
    return 0, holds


def steps(game, machine, dos=None, variant=None, show=None):
    """Captures and builds the image of the game in a folder on a machine,
    and checks it when dos names the folder of the DOS system files. variant
    names a capture variant, in place of the game file's. Returns the Step
    that failed, or else the last one. show gets each Step when it ends."""
    todo = [("capture", capture_step, game, machine, variant), ("build", build_step, game, machine, variant)]
    if dos:
        todo.append(("check", check.check, game, machine, dos))
    for call in todo:
        step = run_step(*call)
        if show:
            show(step)
        if step.status != 0:
            break
    return step


def message(step):
    """A step's end in one line, for Result.message."""
    if step.status == 0:
        return PASS if step.name == "check" else ""
    if step.name == "check" and step.status == 3 and step.output.strip():
        for number, passed, lines in check.points(step.output.strip()):
            if number in (2, 3, 4) and not passed:
                return f"point {number}: fail:" + "".join(lines[:1])
        return step.output.strip().splitlines()[0]
    return (step.error.strip().splitlines() or [f"{step.name}.py failed"])[-1]


def result(step, variant=None, image=None):
    """The Result of the steps that ended with a Step."""
    return Result(step.name if step.status else None, step.status, message(step), step.broke, variant, image)


def run(game, machine, dos=None, try_variants=False, show=None, trying=None):
    """Makes the image of the game in a folder on a machine, and returns the
    Result. The steps are those of steps(), and a pass moves the image to
    images/. With try_variants, when a step fails and the game file names no
    capture variant, the steps run again on each capture variant that the
    machine file lists, and the first that passes gives the result. When none
    passes, the steps run once more with the game file's own lines and without
    the check, to leave their snapshot and image, and the result is the first
    failure. show gets each Step when it ends, and trying each variant's name
    before its trial. An error in the game's or the machine's file between the
    trials is raised as gamefile and msx raise it."""
    first = steps(game, machine, dos, show=show)
    if first.status == 0:
        return result(first, image=gamefile.publish(machine, game))
    # The capture's status 1 is an error in the input files, which every
    # variant has too. The build's is a snapshot that cannot become an image,
    # which another capture can change.
    if not try_variants or (first.status == 1 and first.name == "capture"):
        return result(first)
    named = gamefile.read_game(game, machine).capture
    variants = msx.read_machine(msx.machine_path(machine)).variants
    if named:
        return result(first)
    for variant in variants:
        if trying:
            trying(variant)
        step = steps(game, machine, dos, variant, show)
        if step.status == 0:
            return result(step, variant, gamefile.publish(machine, game))
    if variants:
        # The check's result is known.
        steps(game, machine, show=show)
    return result(first)


def broken(error):
    """The Result of steps that ended without one: a transient failure with
    the last line of error."""
    return Result(None, 2, (error.strip().splitlines() or ["pipeline.py failed"])[-1], True, None, None)


def read_result(status, output, error):
    """The Result that pipeline.py printed as a program, from its exit status
    and what it printed on standard output and standard error. A program that
    ended in a Python error or by a signal printed none, which is a transient
    failure with the last line of its error."""
    if status == 0:
        try:
            return Result(**json.loads(output))
        except (ValueError, TypeError):
            pass
    return broken(error)


def main():
    parser = msx.Parser(description="Make and check a game's image on a machine, and print the result as JSON.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    args = parser.parse_args()
    print(json.dumps(run(gamefile.game_folder(args.game), args.machine, args.dos)._asdict()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
