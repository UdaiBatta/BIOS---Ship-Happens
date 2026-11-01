# MOTIONIQ showreel: asset inventory

Everything here comes from the repository `UdaiBatta/BIOS---Ship-Happens` (commit `39523e4`).
No product UI is redrawn. Every UI pixel in the film is a Playwright screenshot of
`frontend/prototype/index.html`, captured by `../scripts/capture.js`.

## Identity

| Item | Value | Source |
| --- | --- | --- |
| Product name / logo | **MOTIONIQ**. A typographic wordmark (bold, tracking 0.06em). There is no image logo in the repo. | `frontend/prototype/index.html` `.brand`, deck slide 1 |
| Team / event | BIOS · Ship Happens (PS4: 3D hand motion) | `README.md` title |
| One-liner | "Factory POV video holds useful hand motion. Teams need trustworthy cues to find usable seconds." | deck slide 1 |
| Deck font | Arial (rendered here with Liberation Sans, its metric clone) | `slides/MOTIONIQ.pptx`, `scripts/build_submission_slides.py` |
| UI font | `system-ui` stack (renders as Inter in this container) | `index.html` `--font` |

## Colours

| Token | Hex | Where |
| --- | --- | --- |
| Page | `#0d0d0d` | UI `--page` |
| Surface / 2 / 3 | `#1a1a19` / `#222221` / `#2c2c2a` | UI |
| Ink / ink-2 / muted | `#f0efec` / `#c3c2b7` / `#898781` | UI |
| Wearer-left (orange) | `#d95926` (UI), `#D97832` (deck) | UI `--left`, deck accent |
| Wearer-right (blue) | `#3987e5` (UI), `#327DA8` (deck) | UI `--right`, deck accent |
| Warning / good / critical | `#fab219` / `#0ca30c` / `#d03b3b` | UI |
| Deck ink / paper | `#22333B` / `#F8F7F3` | deck |

## Screenshots (`ui/`, DPR 2)

| Folder | What | Real action captured |
| --- | --- | --- |
| `ui/L/` | Desktop layout (1600 px viewport): header, controls, video, 3D, timeline, frame details, events panels + `full.png` | none (initial state, frame 180) |
| `ui/P/` | The UI's own 2-column responsive layout (1080 px viewport), used for the 9:16 assembly | none |
| `ui/L/live`, `ui/P/live` | Video and 3D panels, 30 consecutive frames | clicking **1f ▶** thirty times |
| `ui/f1/` | 3D canvas, 56 frames, plus the Side/Top/Camera and Skeleton/Mesh controls | wheel-zoom then **drag to orbit** the 3D hands |
| `ui/f2/` | Timeline panel + video panel, 57 frame pairs | **drag-scrub** the timeline from 1.6 s to 6.4 s |
| `ui/f3/` | Events, timeline, video, frame-details panels in 5 states | **click "Problems only"**, then **click "Left hand lost"** → seeks to 00:03.600 |
| `ui/brand_wordmark.png` | The product's rendered wordmark (DPR 6) | — |
| `ui/manifest.json` | Panel rectangles and recorded mouse positions (the film's cursor replays these) | — |
| `slides/` | The six deck slides rendered from `slides/MOTIONIQ.pdf` | — |

The viewer prototype runs on **synthetic demo data** (its own badge says so). The film keeps a
small "synthetic demo data" caption on the UI shots.

## The number

The `[METRIC]` slot was left empty in the brief. Accuracy is explicitly **not measured** in this
repo (README, deck slides 4–5), so the film does not invent one. It uses the verified-status line
from `README.md` (1 Nov 2026): **197 pipeline tests passed (1 skipped) + 42/42 backend tests passed =
239 tests passed**. The film was not able to re-run the suite in this session (the sandbox refused to
install the repo's dependencies), so the on-screen source says "README, 1 Nov 2026".

Other real numbers available: 21 landmarks per hand; 970-vertex / 1,872-triangle generated hand
surface; 5,400 / 5,400 frames with identical packet and decoded timestamps; 78 commits from
2 contributors since 1 Aug 2026 (GitHub contributors API).
