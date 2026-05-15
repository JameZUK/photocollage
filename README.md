# Photo Collage Generator for InkyPi

A Flask backend that pulls photos from [Immich](https://immich.app) and serves dynamically generated collages to [InkyPi](https://github.com/fatihak/InkyPi)-driven e-ink displays.

This project was built to drive a two-display setup:

| Display | Endpoint | Resolution | Palette | Purpose |
|---|---|---|---|---|
| Inky Impression 13.3" (top) | `/collage.png` | 1600×1200 | 7-colour | The photo collage |
| Inky wHAT (bottom) | `/info.png` | 400×300 | 4-colour | Layout legend — group letters, dates, and locations matching the collage above |

Both endpoints share a single "current generation" of photos so the legend always describes the collage that's actually on the larger screen.

## How it works

1. On each request, the server picks N photos from your Immich library using one of three weighted strategies (random / on-this-day memories / album), then composes them into a collage with one of two layout algorithms (`grid` or `golden_ratio`, picked automatically by default).
2. Photos are grouped by `(capture date, city/country)` using Immich's pre-computed reverse-geocoded metadata — no Nominatim, no local EXIF parsing.
3. Each group gets a coloured marker (red / yellow / black, plus striped pairs for additional groups). These same markers appear as borders around the relevant photos on `/info.png` and as a colour-coded list of dates+locations.

### The two endpoints

* **`GET /collage.png`** — the main collage. Full-colour RGB PNG. Sized to `display.width × display.height`. Intended for the 7-colour display; do not pre-quantize, the InkyPi driver handles dithering against the device palette.
* **`GET /info.png`** — the legend image. Pre-quantized to the Inky wHAT's 4-colour palette (white background, with red / yellow / black markers) so text and borders render crisply without dithering. Sized to `info_display.width × info_display.height`.
* **`GET /`** — a plain HTML status page listing each group, its marker colour(s), date, and location. Useful for verifying what's being shown without staring at the e-ink panels.

Both image endpoints share one cached "current generation" for `generation.ttl_seconds` (default 30s). The first request after the TTL expires regenerates; subsequent requests within the window serve the cached image. This means you can point two independent InkyPi playlists at the two endpoints and they will stay in sync without coordinating with each other — whichever one fires first triggers the generation.

## Requirements

* [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)
* A reachable Immich instance with an API key (Immich UI → Account → API Keys)
* Two InkyPi instances configured with the `image_url` plugin (one per display)

## Setup

```sh
git clone <this-repo-url>
cd photocollage
```

Edit `config.yaml` and set at minimum:

```yaml
immich:
  base_url: "http://your-immich-host:2283"
  api_key: "your-immich-api-key"
```

Then:

```sh
docker compose up --build -d
docker compose logs -f
```

Point each InkyPi's `image_url` plugin at the appropriate endpoint:

* Big display: `http://<this-host>:8000/collage.png`
* Info display: `http://<this-host>:8000/info.png`

## Configuration reference

`config.yaml` is the only configuration file. All blocks are optional — anything you omit is filled in from `DEFAULT_CONFIG` in `config.py` via deep merge.

```yaml
server:
  host: 0.0.0.0
  port: 8000

display:                          # the big Inky Impression
  width: 1600
  height: 1200

info_display:                     # the small Inky wHAT
  width: 400
  height: 300
  font_settings:                  # paths must exist inside the container
    header:       { path: "/usr/share/fonts/...", size: 11 }
    body:         { path: "/usr/share/fonts/...", size: 11 }
    group_letter: { path: "/usr/share/fonts/...", size: 14 }

immich:
  base_url: "http://immich:2283"
  api_key: ""                     # required
  verify_tls: true                # set false for self-signed LAN certs
  image_size: preview             # 'preview' (fast JPEG) or 'original'

selection:
  weights:                        # weighted random across strategies; 0 disables
    random: 40
    memories: 30
    album: 30
  album_ids: []                   # empty = pick any album with enough photos
  min_assets_per_collage: 4       # fall back to 'random' if a strategy returns less

cache:
  asset_list_ttl_seconds: 300     # in-memory cache for album/memory lookups
  image_dir: "/app/cache"         # empty string disables on-disk image cache
  image_max_bytes: 500000000      # LRU eviction budget

photos:
  layout: auto                    # 'auto' | 'grid' | 'golden_ratio'
  padding: 5
  randomize_order: true
  max_image_size: 800             # downsample before layout for speed
  max_images_per_collage: 5

generation:
  ttl_seconds: 30                 # shared-generation cache for /collage.png + /info.png

debugging:
  enabled: false
```

## Project structure

```
.
├── main.py                # Flask app, GenerationManager, InfoGraphicRenderer
├── collage_generator.py   # Collage composition (grid + golden_ratio layouts)
├── asset_source.py        # Weighted strategy selection + image fetcher with caches
├── immich_client.py       # Thin httpx client for the 5 Immich endpoints used
├── config.py              # DEFAULT_CONFIG + deep-merge loader
├── config.yaml            # Your settings (see below for safety note)
├── Dockerfile             # Multi-stage build, non-root user
└── docker-compose.yml
```

## Keeping your API key out of git

`config.yaml` is tracked in this repo because it doubles as a template — the shipped version has `api_key: ""`. Once you set a real key locally, take **one** of these steps so you don't accidentally commit it:

1. **Tell git to ignore local changes** (simplest):
   ```sh
   git update-index --skip-worktree config.yaml
   ```
   Reverse with `--no-skip-worktree` when you genuinely want to edit the template.

2. **Or move the key out of the file** — set `IMMICH_API_KEY` in your shell / `docker-compose.yml` env block and read it from `config.py` (not currently wired up; small change if you want it).

3. **Or untrack `config.yaml` entirely**: uncomment the `# config.yaml` line in `.gitignore` and `git rm --cached config.yaml`.
```
