#!/usr/bin/env python3
"""Exhaustive product search on Galaxus (galaxus.ch) through its public MCP endpoint."""
from __future__ import annotations

import argparse
import sys

__version__ = "0.1.0"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="galaxus.py")
    parser.add_argument("--version", action="version", version=f"galaxus-skill {__version__}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
