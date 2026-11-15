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

The runtime character layers under `形象/rig/` are not distributed here.
They are derived from "鲸鱼娘形象" by 上善无形 (Bilibili UID 4456176),
licensed CC BY-NC-SA 4.0. See `ASSETS_LICENSE.md` before using any
character assets. The 3D files may constitute adaptations of that work;
the MIT license in this repository does not cover them.

## Run locally

The launcher expects the project layout shown in `docs/`. Start the local
services, then open the page in a browser. `tools/自检.py` runs the full
self-check (syntax, protocol invariants, live page, screenshot check).

## Privacy

No API keys, memory databases, diaries, logs or model weights are included
in this repository. See `.gitignore` for the exclusion list.

Note: personal names and absolute Windows paths in the sample
files have been anonymised for publication.
