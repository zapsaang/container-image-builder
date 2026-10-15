"""Validation shared by the image planner and the version resolver.

Python standard library only, designed for GitHub-hosted runner.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
ALLOWED_PLATFORMS = {"linux/amd64", "linux/arm64"}


def relative_path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"{name} must stay within the upstream repository")
    if value != "." and any(part in ("", ".") for part in value.split("/")):
        raise ValueError(f"{name} must be normalized")
    return value


def read_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name != path.stem:
        raise ValueError(f"{path}: name must match filename, lowercase and path-safe")
    repo = data.get("repository")
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise ValueError(f"{path}: repository must be OWNER/REPO")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"{path}: enabled must be boolean")
    version = data.get("version", {})
    if not isinstance(version, dict) or version.get("strategy") not in ("latest-release", "tag"):
        raise ValueError(f"{path}: strategy must be latest-release or tag")
    if version["strategy"] == "tag" and not (
        isinstance(version.get("tag"), str) and TAG_RE.fullmatch(version["tag"])
    ):
        raise ValueError(f"{path}: invalid pinned tag")
    build = data.get("build", {})
    if not isinstance(build, dict):
        raise ValueError(f"{path}: build must be object")
    context = relative_path(build.get("context", "."), "build.context")
    dockerfile = relative_path(build.get("dockerfile", "Dockerfile"), "build.dockerfile")
    dockerfile_source = build.get("dockerfile_source", "upstream")
    if dockerfile_source not in ("upstream", "local"):
        raise ValueError(f"{path}: dockerfile_source must be upstream or local")
    if dockerfile_source == "local":
        local_file = path.parent.parent / "dockerfiles" / name / dockerfile
        if not local_file.is_file():
            raise ValueError(f"{path}: custom Dockerfile missing: {local_file}")
    dockerfile_path = (
        f"./upstream/{dockerfile}" if dockerfile_source == "upstream"
        else f"./dockerfiles/{name}/{dockerfile}"
    )
    platforms = build.get("platforms", ["linux/amd64", "linux/arm64"])
    if not isinstance(platforms, list) or not platforms or any(p not in ALLOWED_PLATFORMS for p in platforms):
        raise ValueError(f"{path}: unsupported platform; supported: {ALLOWED_PLATFORMS}")
    if len(platforms) != len(set(platforms)):
        raise ValueError(f"{path}: duplicate platforms")
    latest = data.get("publish_latest", version["strategy"] == "latest-release")
    if not isinstance(latest, bool):
        raise ValueError(f"{path}: publish_latest must be boolean")
    if latest and version["strategy"] != "latest-release":
        raise ValueError(f"{path}: publish_latest only supported for latest-release")
    return {
        "name": name,
        "enabled": enabled,
        "repository": repo,
        "strategy": version["strategy"],
        "pinned_tag": version.get("tag", ""),
        "context": context,
        "dockerfile": dockerfile,
        "dockerfile_path": dockerfile_path,
        "platforms": ",".join(platforms),
        "publish_latest": latest,
    }
