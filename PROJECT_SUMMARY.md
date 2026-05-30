# Movie Intelligence Dashboard — Project Summary

## Overview

A fully client-side, single-file HTML dashboard visualizing the IMDB movie metadata dataset (`archive/movie_metadata.csv`, ~5,043 films, 28 columns). No server required — the Python script pre-aggregates all data and bakes it into `dashboard.html` as embedded JSON, making the file deployable to GitHub Pages or any static host as-is.

---

## Files

| File | Role |
|---|---|
| `archive/movie_metadata.csv` | Raw data source (IMDB metadata) |
| `generate_dashboard.py` | Python build script — reads CSV, aggregates data, writes `dashboard.html` |
| `dashboard.html` | Generated output — self-contained, open directly in browser |

---

## Architecture

**Build step (Python):**
- Uses only stdlib (`csv`, `json`, `collections.defaultdict`)
- All aggregations happen here; results are JSON-dumped into the HTML template as the constant `D`
- Helper functions: `to_float`, `to_int`, `avg`

**Runtime (browser):**
- Chart.js loaded from CDN (no other dependencies)
- All filtering, sorting, and re-aggregation done in JS using the embedded `D` object
- A compact `D.gyd` array (genre, year, score, gross, budget, rating per film) powers dynamic re-aggregation on filter change

---

## Dashboard Structure

Six tabbed pages, lazily initialized (charts render only on first visit):

| Page | Key Charts |
|---|---|
| **Overview** | Films/year (bar + rolling avg line), IMDB score trend (gradient area), box office gross trend (gradient area) |
| **Financial Performance** | Budget vs Gross scatter (colored by genre, break-even line), ROI over time (gradient area), Genre avg gross (opacity-scaled bars) |
| **Genre Intelligence** | Genre ROI ranking (green/red intensity bars), Genre avg score (score-colored bars), Genre trends over time (filled area lines) |
| **Director & Cast** | Searchable, sortable, paginated leaderboard (25/page); expandable rows show full filmography |
| **Audience Engagement** | Score vs Votes scatter (per-point color by score bucket), Score distribution histogram (score-colored bars), Content ratings doughnut |
| **Keywords & Reach** | Top keywords by frequency (fading bars), Top keywords by IMDB score (score-colored), Country production (fading bars) |

---

## Features

### Global Year Range Filter
- Dual-thumb range slider spanning 1916–2016
- Tick marks at year/half-decade/decade intervals; floating tooltips show current year
- **Apply** button (disabled when no pending change) and **Reset** button (disabled when already at full range)
- On apply, updates **all** charts across all pages:
  - Overview: movies/year bars, rolling avg line, score trend, gross trend
  - Financial: scatter points, ROI line, genre avg gross bars
  - Genre: genre trends lines, genre ROI bars, genre score bars
  - Engagement: score-vs-votes scatter, score distribution histogram, content ratings doughnut
  - Director leaderboard: recomputed from filtered film sets per director
- Keywords & Reach stays static (no meaningful year dimension)

### Director Leaderboard
- Sort by total gross, avg IMDB score, or film count
- Live search (debounced)
- Pagination (25 rows/page) with page indicator
- Expandable rows showing full filmography (title, year, score, gross)
- Loading overlay on sort/search to signal processing

### Visual Design
- Dark theme (`#0f1117` background, `#1a1d27` surface, `#2a2d3a` borders)
- Canvas gradients on all area/line charts (top color → transparent)
- Per-point coloring on scatter (green ≥ 7.5, blue 6.5–7.5, yellow 5–6.5, red < 5)
- Per-bar coloring on histograms/rankings by score bucket or magnitude
- Opacity-scaled bars (brightest = highest value) for ranked lists
- Inline value labels on select bar charts
- Rolling 5-year average overlay on Movies/Year chart
- Doughnut chart for content ratings with hover % tooltip

---

## Key JS Globals

| Symbol | Purpose |
|---|---|
| `D` | All embedded data (years, scores, scatter, directors, gyd, kpis, …) |
| `COLORS` | Shared palette array |
| `DEF` | Chart.js default options (dark theme, no animation) |
| `activeMin / activeMax` | Current year filter bounds |
| `C` | Live Chart.js instance references keyed by name |
| `INIT` | Tracks which pages have been initialized (lazy loading) |
| `getYearSlice(lo, hi)` | Slices pre-built yearly series to the active range |
| `getGenreProf(lo, hi)` | Dynamically aggregates genre stats from `D.gyd` |
| `getScoreDist(lo, hi)` | Dynamically bins score distribution from `D.gyd` |
| `getContentRatings(lo, hi)` | Dynamically counts content ratings from `D.gyd` |
| `mkGrad(id, top, bot)` | Creates a canvas linear gradient for chart fills |
| `rollingAvg(arr, w)` | Computes rolling average for overlay lines |
| `scoreColor(score, alpha)` | Maps IMDB score → RGBA color (4-bucket scale) |
| `applyYearFilter(lo, hi)` | Central update function; refreshes all initialized charts |

---

## How to Regenerate

```bash
python generate_dashboard.py
# → writes dashboard.html (~3–4 MB with embedded data)
```

Open `dashboard.html` directly in any modern browser. No server needed.
