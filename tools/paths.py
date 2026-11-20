"""Canonical repository directory paths shared across snapcas tools."""
import os

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
BIN = os.path.join(ROOT, "bin")
GAMES = os.path.join(ROOT, "games")
CUSTOM = os.path.join(ROOT, "custom")
MACHINES = os.path.join(ROOT, "machines")
VARIANTS = os.path.join(MACHINES, "capture")
DOWNLOADS = os.path.join(ROOT, "downloads")
IMAGES = os.path.join(ROOT, "images")
OUT = os.path.join(ROOT, "out")
DOS = os.environ.get("DOS_DIR", os.path.join(ROOT, "dos"))
