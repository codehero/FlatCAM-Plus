#!/usr/bin/env python3
"""Validate GRBL pen plotter G-code for the FlatCAM Plus plotter workflow."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FORBIDDEN_SPINDLE_RE = re.compile(r"\bM0?[34]\b", re.IGNORECASE)
UNIT_RE = re.compile(r"\bG2[01]\b", re.IGNORECASE)
ABSOLUTE_RE = re.compile(r"\bG90\b", re.IGNORECASE)
MOTION_RE = re.compile(r"\bG0?([01])\b", re.IGNORECASE)
COORD_RE = re.compile(r"\b([XYZ])\s*(-?\d+(?:[.,]\d+)?)", re.IGNORECASE)


def strip_comments(line: str) -> str:
    line = re.sub(r"\([^)]*\)", "", line)
    line = line.split(";", 1)[0]
    return line.strip()


def parse_coords(line: str) -> dict[str, float]:
    coords: dict[str, float] = {}
    for axis, value in COORD_RE.findall(line):
        coords[axis.upper()] = float(value.replace(",", "."))
    return coords


def validate(path: Path, pen_up_min: float, pen_down_max: float) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    code_lines = [strip_comments(line) for line in raw_lines]
    code_lines = [line for line in code_lines if line]

    has_unit = any(UNIT_RE.search(line) for line in code_lines)
    has_absolute = any(ABSOLUTE_RE.search(line) for line in code_lines)

    if not has_unit:
        errors.append("Missing G20/G21 unit selection.")
    if not has_absolute:
        errors.append("Missing G90 absolute coordinate mode.")

    current_z: float | None = None
    saw_pen_up_before_xy = False

    for line_no, line in enumerate(code_lines, start=1):
        if FORBIDDEN_SPINDLE_RE.search(line):
            errors.append(f"Line {line_no}: forbidden spindle/laser start command: {line}")

        coords = parse_coords(line)
        motion = MOTION_RE.search(line)

        if "Z" in coords and coords["Z"] >= pen_up_min:
            saw_pen_up_before_xy = True

        if motion and {"X", "Y"} & coords.keys():
            is_rapid = motion.group(1) == "0"
            if not saw_pen_up_before_xy:
                errors.append(f"Line {line_no}: XY move appears before a pen-up Z move: {line}")
            if is_rapid and current_z is not None and current_z <= pen_down_max:
                errors.append(f"Line {line_no}: rapid XY travel while pen is down at Z{current_z}: {line}")

        if "Z" in coords:
            current_z = coords["Z"]

    if not any("Z" in parse_coords(line) and parse_coords(line)["Z"] <= pen_down_max for line in code_lines):
        warnings.append("No pen-down Z move was detected.")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GRBL pen plotter G-code.")
    parser.add_argument("gcode", type=Path)
    parser.add_argument("--pen-up-min", type=float, default=0.1)
    parser.add_argument("--pen-down-max", type=float, default=0.0)
    args = parser.parse_args()

    errors, warnings = validate(args.gcode, args.pen_up_min, args.pen_down_max)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        return 1

    print("OK: pen plotter G-code validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
