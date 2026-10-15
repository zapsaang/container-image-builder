#!/usr/bin/env python3
"""Resolve an upstream GitHub release into registry-ready image tags."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from config import REPO_RE, TAG_RE, NAME_RE


def get_latest_release(repository: str, token: str) -> str:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "container-image-builder",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub release API returned HTTP {exc.code} for {repository}") from exc
    return data["tag_name"]


def resolve(repository: str, strategy: str, pinned_tag: str, owner: str, name: str, publish_latest: bool, token: str) -> dict:
    if not REPO_RE.fullmatch(repository) or not NAME_RE.fullmatch(name):
        raise ValueError("Invalid repository or image name")
    if not NAME_RE.fullmatch(owner.lower()):
        raise ValueError("Invalid registry owner")
    if strategy == "latest-release":
        tag = get_latest_release(repository, token)
    elif strategy == "tag":
        tag = pinned_tag
    else:
        raise ValueError("Unsupported version strategy")
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise ValueError(f"Upstream tag is not a safe OCI tag: {tag!r}")
    if publish_latest and strategy != "latest-release":
        raise ValueError("latest can only point to latest-release")
    image = f"ghcr.io/{owner.lower()}/{name}"
    tags = [f"{image}:{tag}"]
    if publish_latest:
        tags.append(f"{image}:latest")
    return {"version": tag, "image": image, "tags": tags}


def main() -> None:
    settings = resolve(
        repository=os.environ["UPSTREAM_REPOSITORY"],
        strategy=os.environ["VERSION_STRATEGY"],
        pinned_tag=os.environ.get("PINNED_TAG", ""),
        owner=os.environ["GITHUB_REPOSITORY_OWNER"],
        name=os.environ["IMAGE_NAME"],
        publish_latest=os.environ.get("PUBLISH_LATEST", "false") == "true",
        token=os.environ.get("GH_TOKEN", ""),
    )
    print(f"Resolved {settings['image']} -> {settings['version']}")
    outputs_file = os.environ["GITHUB_OUTPUT"]
    with open(outputs_file, "a", encoding="utf-8") as output:
        output.write(f"version={settings['version']}\n")
        output.write(f"image={settings['image']}\n")
        output.write("tags<<END_IMAGE_TAGS\n")
        output.write("\n".join(settings["tags"]) + "\n")
        output.write("END_IMAGE_TAGS\n")


if __name__ == "__main__":
    main()
