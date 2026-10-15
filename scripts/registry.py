#!/usr/bin/env python3
"""Plan registry action: build, retag latest, or skip.

This script only inspects registry state. The workflow performs mutations.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

MISSING_RE = re.compile(r"(?:manifest unknown|name unknown|not found|(?:^|\W)404(?:\W|$))", re.I)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class Manifest:
    digest: str
    platforms: frozenset[str]


def _inspect(ref: str, field: str) -> dict | None:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json ." + field + "}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        diagnostic = (result.stderr + "\n" + result.stdout).strip()
        if MISSING_RE.search(diagnostic):
            return None
        raise RuntimeError(f"Registry inspection failed for {ref}: {diagnostic}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid registry inspect output for {ref}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid registry inspect document for {ref}")
    return data


def inspect_image(ref: str) -> Manifest | None:
    manifest = _inspect(ref, "Manifest")
    if manifest is None:
        return None
    digest = manifest.get("digest")
    if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        raise RuntimeError(f"Missing or invalid digest for {ref}")
    platforms: set[str] = set()
    if isinstance(manifest.get("manifests"), list):
        for item in manifest["manifests"]:
            if isinstance(item, dict):
                p = item.get("platform")
                if isinstance(p, dict) and p.get("os") == "linux" and p.get("architecture"):
                    platforms.add(f"linux/{p['architecture']}")
    else:
        image = _inspect(ref, "Image")
        if image and image.get("os") == "linux" and image.get("architecture"):
            platforms.add(f"linux/{image['architecture']}")
    return Manifest(digest=digest, platforms=frozenset(platforms))


def decide(version: Manifest | None, latest: Manifest | None, required: set[str], publish_latest: bool, force: bool) -> str:
    if force or version is None or not required.issubset(version.platforms):
        return "build"
    if publish_latest and (latest is None or latest.digest != version.digest):
        return "retag"
    return "skip"


def main() -> None:
    image = os.environ["REGISTRY_IMAGE"]
    version = os.environ["IMAGE_VERSION"]
    required = set(os.environ["REQUIRED_PLATFORMS"].split(","))
    publish_latest = os.environ.get("PUBLISH_LATEST", "false") == "true"
    force = os.environ.get("FORCE", "false") == "true"

    if force:
        action = "build"
    else:
        existing = inspect_image(f"{image}:{version}")
        latest = (inspect_image(f"{image}:latest") if publish_latest and existing
                  and required.issubset(existing.platforms) else None)
        action = decide(existing, latest, required, publish_latest, force)

    print(f"Registry plan for {image}:{version}: {action}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"action={action}\n")


if __name__ == "__main__":
    main()
