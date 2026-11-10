#!/usr/bin/env python3
"""Runs the tests (docs/PLAN.md, Test setup) in parallel, for make test and
make unit: each test class in a process of its own, or a whole module when it
has setUpModule, so that its setup runs once. Most of the time goes to openMSX,
so the units overlap well.

Usage: run.py [--pure] [--list] [--workers <n>] [filter ...]

--pure runs only the pure tier (tests/support.py, PURE), whose tests start no
openMSX and read no tape, with OPENMSX naming no program, so that a test there
that starts openMSX fails. A filter is a text: the run takes the tests whose
ID, <module>.<class>.<test>, holds one of the filters, as in
"run.py restore service" or "run.py Stops.test_a_cut". --list prints the IDs
of the tests that the run would take, and runs none.

Prints each unit's time, result and number of tests, then the output of each
unit that fails, the tests that were skipped, by reason, and one line with
the totals. A module that cannot be imported is a unit that fails.
Exit status: 0 when every unit passes, or 1: for a test that fails or ends in
an error, for a module that cannot be imported, and for filters that take no
test.
"""
import argparse
import concurrent.futures
import importlib
import json
import os
import subprocess
import sys
import time
import traceback
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def tests_of(suite):
    """The tests of a suite, in its order."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from tests_of(item)
        else:
            yield item


def modules(pure):
    """The names of the test modules to run: all, or the pure tier's."""
    names = sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
    if pure:
        import support
        return [name for name in names if name in support.PURE]
    return names


def units(names, filters):
    """The units, as (module, class or None, the IDs of its tests that the
    filters take), and the modules that cannot be imported, as (module, the
    error's text)."""
    found, broken = [], []
    for name in names:
        try:
            module = importlib.import_module(name)
        except Exception:
            broken.append((name, traceback.format_exc()))
            continue
        classes = [(c, v) for c, v in sorted(vars(module).items())
                   if isinstance(v, type) and issubclass(v, unittest.TestCase) and v.__module__ == name]
        by_class = {c: [t.id() for t in tests_of(unittest.defaultTestLoader.loadTestsFromTestCase(v))]
                    for c, v in classes}
        if hasattr(module, "setUpModule"):
            by_class = {None: [i for ids in by_class.values() for i in ids]}
        for cls, ids in by_class.items():
            ids = [i for i in ids if not filters or any(f in i for f in filters)]
            if ids:
                found.append((name, cls, ids))
    return found, broken


class Result(unittest.TextTestResult):
    """A unit's result, which also keeps each skipped test's reason."""

    def summary(self):
        return {"tests": self.testsRun, "passed": self.wasSuccessful(),
                "skipped": [(test.id(), reason) for test, reason in self.skipped]}


def run_unit(ids):
    """Runs the tests of the IDs in this process, for the unit's process.
    Prints the tests' output on standard error and the result as one line of
    JSON on standard output."""
    suite = unittest.defaultTestLoader.loadTestsFromNames(ids)
    result = unittest.TextTestRunner(stream=sys.stderr, resultclass=Result).run(suite)
    print(json.dumps(result.summary()))
    return 0 if result.wasSuccessful() else 1


def run(unit, env):
    """Runs a unit in a process of its own: its seconds, whether it passed,
    its number of tests, its skipped tests with their reasons, and its
    output."""
    _, _, ids = unit
    start = time.monotonic()
    result = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--unit", *ids],
                            capture_output=True, text=True, env=env)
    seconds = time.monotonic() - start
    try:
        summary = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        # The process ended without its result: it counts as failed.
        return seconds, False, 0, [], result.stderr + result.stdout
    passed = summary["passed"] and result.returncode == 0
    return seconds, passed, summary["tests"], summary["skipped"], result.stderr


def main():
    parser = argparse.ArgumentParser(description="Run the tests in parallel.")
    parser.add_argument("filters", nargs="*", metavar="filter", help="a text in the IDs of the tests to run")
    parser.add_argument("--pure", action="store_true", help="run only the pure tier, without openMSX")
    parser.add_argument("--list", action="store_true", help="print the IDs of the tests, and run none")
    parser.add_argument("--workers", type=int, default=8, help="the number of units to run at once (default: 8)")
    parser.add_argument("--unit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.unit:
        return run_unit(args.filters)

    env = dict(os.environ)
    if args.pure:
        env.update(SNAPCAS_TESTS="pure", OPENMSX=os.path.join(HERE, "no-openmsx-in-the-pure-tier"))
        os.environ.update(env)
    start = time.monotonic()
    found, broken = units(modules(args.pure), args.filters)
    if args.list:
        print("\n".join(i for _, _, ids in found for i in ids))
        for name, error in broken:
            print(f"\n== {name}\n{error}", file=sys.stderr)
        return 1 if broken else 0
    failed = [(f"{name} (not imported)", error) for name, error in broken]
    for name, _ in failed:
        print(f"{0:6.0f}s  FAILED  {name}", flush=True)
    tests, skipped = 0, {}
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(run, unit, env): unit for unit in found}
        for job in concurrent.futures.as_completed(jobs):
            module, cls, _ = jobs[job]
            seconds, passed, count, skips, output = job.result()
            tests += count
            name = f"{module}.{cls}" if cls else module
            for test, reason in skips:
                skipped.setdefault(reason, []).append(test)
            print(f"{seconds:6.0f}s  {'ok' if passed else 'FAILED'}  {name} ({count} tests"
                  + (f", {len(skips)} skipped" if skips else "") + ")", flush=True)
            if not passed:
                failed.append((name, output))
    for name, output in failed:
        print(f"\n== {name}\n{output}")
    for reason, ids in sorted(skipped.items()):
        print(f"\nSkipped, {reason}:\n" + "\n".join(f"  {i}" for i in sorted(ids)))
    if not found and not broken:
        print("no test's ID holds " + " or ".join(args.filters) if args.filters else "no tests")
        return 1
    print(f"\n{tests} tests in {time.monotonic() - start:.0f}s, {sum(map(len, skipped.values()))} skipped, "
          f"{len(failed)} units failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
