# Private reference artifacts and restoration

The source implementation is on the default branch. The authorized factory references are attached to the repository's **private release**, not stored in ordinary source history.

- Repository: https://github.com/UdaiBatta/BIOS---Ship-Happens
- Release tag: `ps4-baseline-handoff-20261031`
- Baseline implementation commit: `5e3ef3e58355b7bed992d9db05201a27f2244f10`
- Detailed continuation instructions: [AGENT_CONTINUATION_PROMPT.md](AGENT_CONTINUATION_PROMPT.md)

Open the repository's Releases page while signed in to an account with repository access and select that tag. A public-looking link does not grant access to a private repository. No credentials or temporary signed URLs are included in the source.

## Asset set

| Asset | Size | Purpose |
| --- | ---: | --- |
| `Final-Team-Plan-v3-PS4-1.pdf` | 0.93 MiB | Unchanged user-supplied 27-page research/team plan. |
| `ps4-demos-and-data.zip` | 82.36 MiB | Three processed 30-second demos; cached raw/filtered data, metrics, events, manifests, annotation templates, and a replay screenshot. |
| `ps4-interactive-replays.zip` | 645.81 MiB | Original and corrected Rerun recordings for all three benchmark configurations. |
| `ps4-source-video.zip` | 103.53 MiB | One complete original factory video plus the 40-clip Drive inventory. |
| `ASSET_MANIFEST.json` | approximately 12 KiB | SHA-256 and byte size for archive entries and assets, source provenance, restoration paths, scope. |
| `SHA256SUMS` | small text file | SHA-256 checksums for the PDF, archives, and manifest. |

The source archive contains the **entire downloaded 180-second original**, not a recompressed substitute. All three 30-second processed benchmark videos are included. Both historical and corrected interactive recordings are retained. The annotation template remains unreviewed and cannot be treated as ground truth.

**Scope:** 40 original clips were inventoried, but only one was downloaded and tested. The other 39 originals have not been duplicated on GitHub. Their canonical private Drive links are preserved in the inventory within `ps4-source-video.zip`. An authorized agent can obtain them from Drive for development/holdout work. Do not report all 40 as processed or evaluated.

The PDF is preserved unchanged, including its own research citations and internal-use notices. Its proposed fisheye/PnP, anatomical identity, bone calibration, robot export, and mesh upgrades remain proposals; the current implementation and measured report define what exists.

## Download with an authenticated account

GitHub CLI example (authenticate normally with an account that has access; do not paste tokens into source or logs):

```sh
gh repo clone UdaiBatta/BIOS---Ship-Happens
cd BIOS---Ship-Happens
gh release download ps4-baseline-handoff-20261031 --repo UdaiBatta/BIOS---Ship-Happens --dir handoff-assets
```

Alternatively, use the signed-in browser and download the six release assets. If you only need to rerun inference, the source video and evidence archives are enough; the large interactive-recording archive is optional because the replay command can regenerate it from the cache and source video.

Verify `SHA256SUMS` with `sha256sum -c SHA256SUMS` on Linux or `shasum -a 256 -c SHA256SUMS` on macOS from the asset directory. Cross-platform verification:

```sh
python -c "import hashlib,pathlib; p=pathlib.Path('handoff-assets'); rows=[s.split('  ',1) for s in (p/'SHA256SUMS').read_text().splitlines()]; checks=[(n,hashlib.file_digest((p/n).open('rb'),'sha256').hexdigest()==h) for h,n in rows]; print(*checks,sep='\n'); assert all(ok for _,ok in checks)"
```

Manifest SHA-256 at packaging: `a7cfa590474bc6a93f5c1335cae5b7eabae474b34ada23475eba2744375438d8`.

## Restore into a clean checkout

The archive paths are rooted at the project directory. Run these commands from a **clean checkout** to avoid overwriting newer local experiments:

```sh
python -m zipfile -e handoff-assets/ps4-source-video.zip .
python -m zipfile -e handoff-assets/ps4-demos-and-data.zip .
python -m zipfile -e handoff-assets/ps4-interactive-replays.zip .
uv sync --frozen --extra dev --extra viewer
uv run motioniq doctor
uv run motioniq fetch-model
uv run pytest -q
```

The third extraction is optional. The original MediaPipe task model is fetched from its versioned official URL; model hashes are in the run manifests. Third-party research code, MANO assets, and model weights are not bundled.

Expected restored paths:

```text
data/private/mytronlabs-000060-016.mp4
data/private/drive_inventory.json
data/private/annotations_first30/
runs/baseline_30s/
runs/persistent_30s/
runs/rescue_30s/
runs/viewer_qa/browser_replay.jpg
```

Use `replay_review.rrd` for the corrected display camera and bounded hand spacing. `replay.rrd` is the original historical recording. Both are hand-relative reconstructions, not factory/world coordinates.

## Access and handling

The user authorized this reference set for continuation by collaborators with access to this **private repository**. Keep the repository private while it contains restricted releases. Do not mirror the footage, PDF, motion data, labels, or recordings into a public repository, public slides, a public website, or another service without authorization. The source-tree ignore rules stay in place. Verify organizer-specific access and retention requirements rather than treating a planning document as the official rules.

A future public source submission must be prepared separately without restricted release assets, footage, labels, or geometry. Do not change this repository's visibility as a shortcut. Changes to sharing and deletion of assets require explicit authorization.

## Relevant primary documentation

- [GitHub release access and asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases): repository read access governs releases; release assets support larger files than browser source uploads.
- [Authenticated release downloads with GitHub CLI](https://cli.github.com/manual/gh_release_download).
- [OpenCV PnP pose computation](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html) and [fisheye camera model](https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html): starting references for the unimplemented geometry prototype.
