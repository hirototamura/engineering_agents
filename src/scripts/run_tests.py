#!/usr/bin/env python3
"""Run the test suite (wrapper around pytest)."""

from __future__ import annotations

import sys

import pytest


def main() -> int:
    args = ["-q", "tests", *sys.argv[1:]]
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
