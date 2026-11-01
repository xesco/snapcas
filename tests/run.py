#!/usr/bin/env python3
"""Runs the tests (docs/PLAN.md) in parallel, for make test: each test class in
a process of its own, or a whole module when it has setUpModule, so that its
setup runs once. Most of the time goes to openMSX, so the units overlap well.

Usage: run.py [workers]

Prints each unit's time and result, and the output of each unit that fails.
Exit status: 0 when every unit passes, or 1.
"""
import concurrent.futures
import os
import re
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def units():
    """The units, as (module, class or None)."""
    found = []
    for name in sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py")):
        module = __import__(name)
        if hasattr(module, "setUpModule"):
            found.append((name, None))
            continue
        found += [(name, c) for c, v in sorted(vars(module).items())
                  if isinstance(v, type) and issubclass(v, unittest.TestCase) and v.__module__ == name]
    return found


def run(unit):
    """Runs a unit: its seconds, whether it passed, its number of tests, and
    its output."""
    module, cls = unit
    command = [sys.executable, "-I", "-m", "unittest", "discover", "-s", HERE, "-p", f"{module}.py"]
    if cls:
        command += ["-k", f"{module}.{cls}."]
    start = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True)
    ran = re.search(r"^Ran (\d+) test", result.stderr, re.M)
    return time.monotonic() - start, result.returncode == 0, int(ran.group(1)) if ran else 0, result.stderr


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    start = time.monotonic()
    failed, tests = [], 0
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        jobs = {pool.submit(run, unit): unit for unit in units()}
        for job in concurrent.futures.as_completed(jobs):
            module, cls = jobs[job]
            seconds, passed, count, output = job.result()
            tests += count
            name = f"{module}.{cls}" if cls else module
            print(f"{seconds:6.0f}s  {'ok' if passed else 'FAILED'}  {name} ({count} tests)", flush=True)
            if not passed:
                failed.append((name, output))
    for name, output in failed:
        print(f"\n== {name}\n{output}")
    print(f"\n{tests} tests in {time.monotonic() - start:.0f}s, {len(failed)} units failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
