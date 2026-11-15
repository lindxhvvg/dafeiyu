# Dafeiyu (大肥鱼 / 小飞鱼)

A local-first AI desktop companion: the body and memory live on your own
machine, while language capability comes from interchangeable model backends.
This repository contains the source, design documents and 3D assets.

> Status: personal learning project. Work in progress, not a production service.

## What is inside

- `src/` — web front end, soul/memory layer, WebSocket server
- `tools/` — self-check, watchdog, launchers, LAN page server
- `docs/` — architecture, construction plan, deployment notes
- `3d/` — GLB / STL / OBJ models and previews (generated 2026-11-01)
- `firmware/` — two Arduino `.ino` sketches for the head mechanism
- `LICENSE` — MIT for original code and documents
- `ASSETS_LICENSE.md` — separate terms for character artwork

## Character artwork is NOT included

The runtime 2D character layers are not distributed here. The character
originates from "溟月 / 鲸鱼娘形象" by 上善无形 (Bilibili UID 4456176) and
the maid-whale redesign by ZipZipPipe, both published under CC BY-NC-SA 4.0.

The 3D files in `3d/` are adaptations and are shared under **CC BY-NC-SA
4.0** as their Adapter's License (see `3d/LICENSE.md` and `NOTICE.md`).
Original code and documents are MIT (`LICENSE`). CC BY-NC-SA 4.0 is not an
open-source license under the OSI definition because it forbids commercial
use; what is open-sourced here is the code. See `ASSETS_LICENSE.md` for the
full attribution chain and conditions.

## Run locally

The launcher expects the project layout shown in `docs/`. Start the local
services, then open the page in a browser. `tools/自检.py` runs the full
self-check (syntax, protocol invariants, live page, screenshot check).

## Privacy

No API keys, memory databases, diaries, logs or model weights are included
in this repository. See `.gitignore` for the exclusion list.

Note: personal names and absolute Windows paths in the sample
files have been anonymised for publication.

## License display

GitHub shows this repository's license as "Other" because it contains two
licenses: MIT for code and CC BY-NC-SA 4.0 for the 3D assets. Read
`ASSETS_LICENSE.md` for a section-by-section compliance self-check.

## Downstream use

The repository imposes no extra conditions on reusers; see "Downstream use
and responsibility" in `ASSETS_LICENSE.md` for what the license itself says
about warranties, liability and continuing obligations.

If a rights holder objects to any file, see "If a rights holder
objects" in `ASSETS_LICENSE.md`.
