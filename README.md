# Therblig

Automatic motion study from a head camera: what each hand touched, for how long, and where the workstation wastes hand motion. Every number links to the frame that proves it.

Hackathon entry for **Problem Statement 2 (what is the hand touching?)**, built on top of reliable two-hand tracking (PS1).

> Status: setting up. No performance numbers are claimed yet.

## One-time setup (every teammate, right after cloning)

```bash
git config core.hooksPath .githooks
```

This turns on the compliance pre-commit hook. It rejects:
- any image or video outside `docs/synthetic/`
- arrays, caches and model files (`.npy`, `.pkl`, `.jsonl`, `.pth`, `.task`, ...)
- anything in `data/`, `outputs/`, `frames/` or `labels/`
- any file over 2 MB

## Where data lives

Hackathon footage, labels and real outputs **never go in this repo**. Keep them in `~/hackathon_data/` (outside the repo).
Only images made from our own recorded bench clip, with no faces, screens or documents, may go in `docs/synthetic/`.

## Before making the repo public

```bash
scripts/check_history.sh
```

This scans the full git history for media, data or model files and for anything over 2 MB.

## Licences

Third-party model licences will be listed here as components are added. Note that WiLoR and MANO are non-commercial.
