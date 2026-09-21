# Tape

**SQLite para videos largos.**

Tape convierte un video largo en un índice temporal chico, local y consultable — y después te deja cortar y comprimir desde ese índice.

```text
video.mp4  →  video.mp4.tape  →  SQL / detect / clips / digest
```

No es un editor. No es una API en la nube. Es una **base de datos temporal embebida** al lado de tu archivo.

## Por qué

Los videos largos son, en su mayoría, tiempo muerto. La mayoría de los pipelines igual suben y procesan todo.

Tape hace lo contrario:

1. **Indexa señales baratas en local** (movimiento, energía de audio)
2. **Consulta la línea de tiempo** (SQL)
3. **Corta solo lo que importa** (ffmpeg)

## Quickstart

Requisitos:

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) en tu `PATH` (`brew install ffmpeg`)

```bash
git clone https://github.com/EmanuelCorreaAR/tape.git
cd tape
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

tape index lecture.mp4
tape info lecture.mp4
tape sql lecture.mp4 "SELECT t0, t1, motion, audio_rms FROM timeline_bins WHERE motion > 0.3 LIMIT 20"
tape detect lecture.mp4
tape compress lecture.mp4 --out digest.mp4
```

La promesa del demo:

```bash
tape compress long.mp4 --out digest.mp4
# 2h → ~15–25m de segmentos activos (depende del contenido y los umbrales)
```

## Comandos

| Comando | Qué hace |
|---------|----------|
| `tape index VIDEO` | Arma `VIDEO.tape` (SQLite) con bins de motion/audio cada 1s |
| `tape info TARGET` | Muestra duración, bins y segmentos |
| `tape sql TARGET "SELECT …"` | Consulta el índice |
| `tape detect TARGET` | Escribe segmentos `activity` a partir de los bins |
| `tape segments TARGET` | Lista segmentos |
| `tape clip TARGET --out clips/` | Exporta clips por segmento |
| `tape compress TARGET --out digest.mp4` | Deja solo actividad → un digest |

`TARGET` puede ser el video o el archivo `.tape`.

## Schema (v0)

El archivo `.tape` es SQLite:

- `media` — path, duración, tamaño, hash parcial
- `timeline_bins` — grilla fija (`motion`, `audio_rms`, `audio_onset`, `luma`)
- `segments` — intervalos derivados (`kind`, `start_s`, `end_s`, `score`, `source`)
- `meta` — `tape_version`, parámetros

Podés inspeccionarlo con:

```bash
sqlite3 lecture.mp4.tape ".schema"
```

## Principios de diseño

1. **Local-first** — el indexado corre en tu máquina
2. **Proxy ≠ original** — entendés barato, cortás del source
3. **SQL es la interfaz** — el índice es inspeccionable y portable
4. **Plugins después** — el core guarda señales; el significado (speech, deportes, CCTV) se enchufa
5. **Barato por defecto** — CPU, ~1 fps de sampling, sin GPU

## Non-goals (por ahora)

- UI tipo NLE / timeline completa
- Pipeline de upload a la nube
- Modelos de ML obligatorios
- Reemplazar ffmpeg

## Estado

**v0.1 alpha** — útil para experimentos y demos. El schema puede evolucionar; `tape_version` vive en `meta`.

## Licencia

MIT
