#!/usr/bin/env python3
"""Build an Actions JSON matrix from images/*.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from config import NAME_RE, read_config


def make_plan(directory: Path, selected: str) -> list[dict]:
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"No image definitions found in {directory}")
    all_configs = [read_config(p) for p in paths]
    if selected != "all" and not NAME_RE.fullmatch(selected):
        raise ValueError("Image filter must be 'all' or an image name")
    if selected != "all" and not any(c["name"] == selected for c in all_configs):
        raise ValueError(f"Unknown image: {selected}")
    matches = [c for c in all_configs if c["enabled"] and (selected == "all" or c["name"] == selected)]
    if selected != "all" and not matches:
        raise ValueError(f"Selected image disabled: {selected}")
    return matches


def main() -> None:
    selected = os.environ.get("IMAGE_FILTER") or "all"
    configs = make_plan(Path("images"), selected)
    print("Selected:", ", ".join(c["name"] for c in configs) or "(none)")
    outputs = {"matrix": json.dumps({"include": configs}, separators=(",", ":")), "count": str(len(configs))}
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as out:
            for key, value in outputs.items():
                out.write(f"{key}={value}\n")
    else:
        print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
