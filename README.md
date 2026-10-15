# Container Image Builder

A single GitHub repository (`container-image-builder`) that builds images from multiple upstream GitHub projects into separate GHCR packages.

## Quick start

1. Create a GitHub repository called `container-image-builder` and push this directory to its `main` branch. (The name is a recommendation, not a functional dependency.)
2. Enable GitHub Actions; check **Settings → Actions → General → Workflow permissions** to ensure package publishing via `GITHUB_TOKEN` is allowed (job grants `packages: write`).
3. Run **Actions → Publish container images → Run workflow** (image = `all`, force = false).
4. Once the workflow finishes, browse your GitHub **Packages** section. On first publication GHCR packages are private by default.

By default it builds only `ssh-mcp` from `tufantunc/ssh-mcp` latest stable GitHub Release. `images/second-image.json` is disabled and is a template for adding more packages.

## Add another image

Create `images/my-tool.json`:

```json
{
  "name": "my-tool",
  "enabled": true,
  "repository": "OWNER/REPOSITORY",
  "version": { "strategy": "latest-release" },
  "build": {
    "context": ".",
    "dockerfile": "Dockerfile",
    "platforms": ["linux/amd64", "linux/arm64"]
  },
  "publish_latest": true
}
```

The upstream must have a root Dockerfile and at least one published GitHub non-prerelease Release for `latest-release`.
If it publishes tags but no Releases, use `"version": { "strategy": "tag", "tag": "v1.2.3" }` and `"publish_latest": false`.
`context` is relative to the upstream checkout. By default, `dockerfile` is also relative to upstream.
For projects without a suitable upstream Dockerfile, put your own Dockerfile in
`dockerfiles/my-tool/Dockerfile` and add `"dockerfile_source": "local"` under `build`.
The local Dockerfile builds with upstream source as the context, so `COPY . .` reads the upstream checkout.
Local Dockerfiles are checked for existence during planning.

On push, the workflow checks all enabled images and builds only missing or incomplete version manifests; on schedule, it polls every 6 hours; manual dispatch accepts the single image name and `force=true` to rebuild. `latest` is only emitted for `latest-release` to avoid accidentally moving it backwards with a pinned historical version. If an existing version image is complete but `latest` points elsewhere, the workflow repairs the tag with `docker buildx imagetools create` without rebuilding.

Example output:

```text
ghcr.io/<owner>/ssh-mcp:v2.19.1
ghcr.io/<owner>/ssh-mcp:latest
ghcr.io/<owner>/my-tool:v1.2.3
```

`<owner>` is the GitHub account or organization that owns the build repository, lowercased for registry naming.

## Release, reproducibility and security

- `latest-release` uses `GET /repos/{owner}/{repo}/releases/latest`; GitHub's latest means the release GitHub currently designates latest, not a semver sort. Drafts and prereleases are ignored.
- Each package has a separate build matrix job (`fail-fast: false`) and isolated cache. Missing upstream releases fail only their own job.
- The version manifest is checked for required platforms (`linux/amd64`, `linux/arm64`), and `latest` is compared with the version manifest by digest. Network or registry authorization errors cause a failed job instead of silently claiming the image is absent.
- `force=true` intentionally rebuilds the same version even if the registry tag exists. Reproducibility still depends on upstream Dockerfile base-image and dependency pinning.
- The workflow checks out upstream source. Treat upstream Dockerfile `RUN` steps as untrusted code; do not expose host secrets or privileged/self-hosted runners to them. For security-sensitive services, enable branch protection/reviews on image definitions.
- SBOM and build provenance metadata are attached. Optional vulnerability scanning, signature enforcement, and integration tests can be added as a separate promotion stage.
- Upstream tags can theoretically be moved. For higher assurance, resolve the tag to its commit SHA in a lockfile and require a review before promoting to production.
- Do not automatically deploy `:latest` to production; use a version or immutable digest and require a separate verified rollout.

## Known boundaries

- Supports GitHub-hosted upstreams with Dockerfiles, and tracking `latest-release` or a pinned Git tag. Other registries or branch-head tracking can be added in the resolver.
- Works best on GitHub-hosted Ubuntu runners. ARM64 is emulated using QEMU. Large builds will benefit from native ARM64 runners.
- `GITHUB_TOKEN` publishes packages associated with this build repository. A pre-existing unrelated GHCR package may need to be connected to the build repository first.
- GitHub scheduled Actions can be delayed; schedules on public inactive repos may be disabled after 60 days. Use a private repo for this internal builder or maintain activity.
- Platform validation checks OCI index descriptors; it cannot prove that platform images boot or pass integration tests. A manually tampered upstream tag may require `force=true`.

## Testing boundaries

The included unit tests validate image definition parsing, version resolution behavior, GHCR manifest inspection and tag planning. They do not run upstream projects' unit or integration tests. Container images are compiled by their Dockerfiles; add project-specific smoke tests before promoting new versions into production.

## Local checks

```bash
python3 scripts/plan.py
python3 -m unittest discover -s tests -v
```

No personal access token is needed for the GitHub Actions publication workflow. Private GHCR image pulls outside Actions require registry credentials.
