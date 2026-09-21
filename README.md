# Tape

**SQLite para videos largos.**

[![PyPI](https://img.shields.io/pypi/v/tape-video.svg)](https://pypi.org/project/tape-video/)
[![License](https://img.shields.io/pypi/l/tape-video.svg)](https://github.com/EmanuelCorreaAR/tape/blob/main/LICENSE)

Tape convierte un video largo en un índice temporal chico, local y consultable — y después te deja cortar y comprimir solo lo activo.

```text
video.mp4  →  video.mp4.tape  →  SQL / clips / digest.mp4
```

No es un editor. No es una API en la nube. Es una **base de datos temporal embebida** al lado de tu archivo.

## Instalación

```bash
pip install tape-video
brew install ffmpeg   # requerido en el PATH
tape doctor
```

Desde el repo (desarrollo):

```bash
git clone https://github.com/EmanuelCorreaAR/tape.git
cd tape
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
tape doctor
```

## Uso rápido

Un solo comando:

```bash
tape digest lecture.mp4 --out digest.mp4
```

Eso indexa (si hace falta), detecta tramos activos y genera:

| Archivo | Qué es |
|---------|--------|
| `lecture.mp4.tape` | Índice SQLite (línea de tiempo) |
| `digest.mp4` | Video solo con tramos activos |
| `digest.mp4.txt` | Resumen legible (criterio + lista de tramos) |
| `digest.mp4.json` | Misma info en JSON |

En la terminal vas a ver una timeline:

```text
Timeline: |██··████·█··███····█|
          █ activo   · quieto/silencio
```

Y un resumen tipo:

```text
Digest listo
  1h 32m  →  18m  (20% del original)
```

## Paso a paso

```bash
tape index lecture.mp4
tape info lecture.mp4
tape detect lecture.mp4
tape compress lecture.mp4 --out digest.mp4

# consultar el índice
tape sql lecture.mp4 "SELECT t0, t1, motion, audio_rms FROM timeline_bins WHERE motion > 0.3 LIMIT 20"
```

Ajustar sensibilidad:

```bash
tape digest video.mp4 --out digest.mp4 --motion 0.08 --audio 0.12
```

## Comandos

| Comando | Qué hace |
|---------|----------|
| `tape doctor` | Chequea ffmpeg y el entorno |
| `tape digest VIDEO --out digest.mp4` | Todo en uno: indexar + comprimir |
| `tape index VIDEO` | Arma `VIDEO.tape` (movimiento + audio) |
| `tape info TARGET` | Duración, muestras, tramos y timeline |
| `tape detect TARGET` | Marca tramos `activity` |
| `tape segments TARGET` | Lista tramos guardados |
| `tape clip TARGET --out clips/` | Exporta cada tramo como `.mp4` |
| `tape compress TARGET --out digest.mp4` | Digest + `.txt` + `.json` |
| `tape sql TARGET "SELECT …"` | SQL sobre el índice |

`TARGET` puede ser el video o el archivo `.tape`.

## Cómo decide qué es “activo”

Hoy es una heurística barata (no IA):

- Por cada segundo mide **movimiento** (cambio entre frames) y **audio** (RMS)
- Un segundo es activo si `motion ≥ 0.12` **o** `audio ≥ 0.18` (defaults)
- Junta segundos activos, fusiona huecos cortos y descarta tramos &lt; 2s

Sirve como baseline para clases, screen recordings, CCTV, etc.  
Para casos finos (p. ej. rallies de pádel) se itera el detector encima del mismo índice.

## Schema (v0)

El archivo `.tape` es SQLite:

- `media` — path, duración, tamaño, hash parcial
- `timeline_bins` — grilla fija (`motion`, `audio_rms`, `audio_onset`, `luma`)
- `segments` — intervalos derivados (`kind`, `start_s`, `end_s`, `score`, `source`)
- `meta` — `tape_version`, parámetros

```bash
sqlite3 lecture.mp4.tape ".schema"
```

## Principios de diseño

1. **Local-first** — el indexado corre en tu máquina
2. **Proxy ≠ original** — entendés barato, cortás del source
3. **SQL es la interfaz** — el índice es inspeccionable y portable
4. **Plugins después** — el core guarda señales; el significado se enchufa
5. **Barato por defecto** — CPU, ~1 fps de sampling, sin GPU

## Non-goals (por ahora)

- UI tipo NLE / timeline completa
- Pipeline de upload a la nube
- Modelos de ML obligatorios
- Reemplazar ffmpeg

## Estado

**v0.1.2** en [PyPI](https://pypi.org/project/tape-video/) — útil para experimentos y demos.  
El schema puede evolucionar; `tape_version` vive en `meta`. Ver [CHANGELOG.md](CHANGELOG.md).

## Apoyar el proyecto

Si Tape te sirve, podés invitarme un cafecito: [cafecito.app/emacorreadev](https://cafecito.app/emacorreadev)

## License

Apache License 2.0
