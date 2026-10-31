# EgoHand Twin

Real factory hands, rebuilt in 3D from a head camera, with an honest confidence label on every frame, and exportable as robot training data.

Hackathon entry for **Problem Statement 4 (3D hand motion)**, built on top of reliable two-hand tracking (PS1).

> Status: setting up. No performance numbers are claimed yet.

## Repo layout

- `frontend/`: offline viewer prototype (open `frontend/prototype/index.html`). See `frontend/README.md`.
- `schema/`: per-frame output schema (`egohand_twin_frame.schema.json`, JSON Schema 2020-12) and a synthetic example record.
- `scripts/`, `.githooks/`: compliance checks.

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
