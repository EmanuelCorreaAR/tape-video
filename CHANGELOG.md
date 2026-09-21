# Changelog

## 0.1.3 — 2026-09-21

- CLI más claro: paneles, epilog con ejemplos, atajos `-o/-m/-a/-f`
- Default inteligente: `tape digest video.mp4` → `video_digest.mp4`
- Barra de progreso al cortar tramos
- `doctor` muestra versión de ffmpeg

## 0.1.2 — 2026-09-21

- `tape digest` — todo en uno (index + compress)
- `tape doctor` — chequea ffmpeg / entorno
- Timeline visual en terminal (`█` activo / `·` quieto)

## 0.1.1 — 2026-09-21

- Output del CLI en español y más legible
- Tiempos en formato humano (`1h 32m`, `01:05`)
- `compress` escribe `digest.mp4.txt` con criterio + lista de tramos
- JSON del digest incluye tramos con timestamps
- Licencia Apache 2.0
- Sección de apoyo (cafecito) en el README

## 0.1.0 — 2026-09-21

- Primera versión alpha
- CLI: `index`, `info`, `sql`, `detect`, `segments`, `clip`, `compress`
- Schema SQLite v0 (media, timeline_bins, segments, meta)
- README en español
