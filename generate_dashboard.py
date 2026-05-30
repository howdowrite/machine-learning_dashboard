import csv
import json
from collections import defaultdict

CSV_PATH = "archive/movie_metadata.csv"
OUT_PATH = "dashboard.html"

# ── Load ──────────────────────────────────────────────────────────────────────

rows = []
with open(CSV_PATH, encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        rows.append(row)

def to_float(val):
    try:
        v = float(val)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None

def to_int(val):
    try:
        v = int(float(val))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None

def avg(lst):
    return round(sum(lst) / len(lst), 2) if lst else None

# ── Year aggregations ─────────────────────────────────────────────────────────

year_counts  = defaultdict(int)
year_scores  = defaultdict(list)
year_gross   = defaultdict(float)
year_budget  = defaultdict(list)
year_genres  = defaultdict(lambda: defaultdict(int))

for r in rows:
    yr = to_int(r.get("title_year", ""))
    if yr is None or yr > 2016:
        continue
    year_counts[yr] += 1
    s = to_float(r.get("imdb_score", ""))
    if s: year_scores[yr].append(s)
    g = to_float(r.get("gross", ""))
    if g: year_gross[yr] += g / 1e6
    b = to_float(r.get("budget", ""))
    if b: year_budget[yr].append(b / 1e6)
    genre_raw = r.get("genres", "")
    if genre_raw:
        fg = genre_raw.split("|")[0].strip()
        if fg: year_genres[yr][fg] += 1

years = sorted(year_counts.keys())

genre_totals = defaultdict(int)
for yd in year_genres.values():
    for g, c in yd.items():
        genre_totals[g] += c
top5_genres = [g for g, _ in sorted(genre_totals.items(), key=lambda x: -x[1])[:5]]
TOP8_GENRES = [g for g, _ in sorted(genre_totals.items(), key=lambda x: -x[1])[:8]]

movies_per_year = [year_counts[y] for y in years]
avg_score_yr    = [round(sum(year_scores[y])/len(year_scores[y]),2) if year_scores[y] else None for y in years]
total_gross_yr  = [round(year_gross[y],1) if year_gross[y] else None for y in years]
avg_budget_yr   = [round(sum(year_budget[y])/len(year_budget[y]),1) if year_budget[y] else None for y in years]
genre_series    = {g: [year_genres[y].get(g,0) for y in years] for g in top5_genres}

# ── Global KPIs ───────────────────────────────────────────────────────────────

total_films = len(rows)
all_scores  = [to_float(r["imdb_score"]) for r in rows if to_float(r.get("imdb_score"))]
global_avg_score = round(sum(all_scores)/len(all_scores), 2) if all_scores else 0

valid_gy = {y: year_gross[y] for y in years if year_gross[y]}
peak_yr  = max(valid_gy, key=valid_gy.get) if valid_gy else "N/A"
peak_val = round(valid_gy[peak_yr], 0) if valid_gy else 0

yr_min = min(to_int(r["title_year"]) for r in rows if to_int(r.get("title_year")))
yr_max = max(to_int(r["title_year"]) for r in rows if to_int(r.get("title_year")))

# ── Director aggregation ──────────────────────────────────────────────────────

director_map = defaultdict(list)
for r in rows:
    name = r.get("director_name", "").strip()
    if not name: continue
    gv = to_float(r.get("gross", ""))
    director_map[name].append({
        "t": r.get("movie_title", "").strip(),
        "y": to_int(r.get("title_year", "")) or 0,
        "s": to_float(r.get("imdb_score", "")),
        "g": round(gv / 1e6, 1) if gv else None,
    })

director_stats = []
for name, films in director_map.items():
    sc = [f["s"] for f in films if f["s"]]
    gr = [f["g"] for f in films if f["g"] is not None]
    best = max(films, key=lambda f: f["s"] or 0)
    director_stats.append({
        "name":        name,
        "count":       len(films),
        "avg_score":   round(sum(sc)/len(sc),2) if sc else None,
        "total_gross": round(sum(gr),1) if gr else 0,
        "best":        best["t"],
        "films":       sorted(films, key=lambda f: f["y"]),
    })
director_stats.sort(key=lambda d: -d["total_gross"])

# ── Financial: scatter (budget vs gross) ──────────────────────────────────────

scatter_data = []
for r in rows:
    b = to_float(r.get("budget", ""))
    g = to_float(r.get("gross", ""))
    if not b or not g: continue
    genre = r.get("genres","").split("|")[0].strip() or "Other"
    if genre not in TOP8_GENRES: genre = "Other"
    yr = to_int(r.get("title_year","")) or 0
    roi = round((g - b) / b * 100, 1)
    scatter_data.append({
        "x":  round(b/1e6, 1),
        "y":  round(g/1e6, 1),
        "r":  roi,
        "t":  r.get("movie_title","").strip(),
        "g":  genre,
        "yr": yr,
        "s":  to_float(r.get("imdb_score","")),
    })

roi_by_yr_map = defaultdict(list)
for d in scatter_data:
    if d["yr"]: roi_by_yr_map[d["yr"]].append(d["r"])
roi_series = [round(sum(roi_by_yr_map[y])/len(roi_by_yr_map[y]),1) if roi_by_yr_map.get(y) else None for y in years]

all_roi = [d["r"] for d in scatter_data]
avg_roi_global  = round(sum(all_roi)/len(all_roi), 1) if all_roi else 0
profitable_count = sum(1 for d in scatter_data if d["r"] > 0)

# ── Genre profitability (static, all years) ───────────────────────────────────

gp_map = defaultdict(lambda: {"gross":[], "budget":[], "score":[], "count":0})
for r in rows:
    genre = r.get("genres","").split("|")[0].strip()
    if not genre: continue
    gp_map[genre]["count"] += 1
    g = to_float(r.get("gross","")); b2 = to_float(r.get("budget","")); s2 = to_float(r.get("imdb_score",""))
    if g:  gp_map[genre]["gross"].append(g/1e6)
    if b2: gp_map[genre]["budget"].append(b2/1e6)
    if s2: gp_map[genre]["score"].append(s2)

genre_prof = []
for genre, d in gp_map.items():
    if d["count"] < 5: continue
    ag = round(sum(d["gross"])/len(d["gross"]),1) if d["gross"] else 0
    ab = round(sum(d["budget"])/len(d["budget"]),1) if d["budget"] else 0
    ar = round((ag-ab)/ab*100,1) if ab > 0 else 0
    as_ = round(sum(d["score"])/len(d["score"]),2) if d["score"] else 0
    genre_prof.append({"genre":genre,"count":d["count"],"avg_gross":ag,"avg_budget":ab,"avg_roi":ar,"avg_score":as_})
genre_prof.sort(key=lambda x: -x["avg_gross"])

best_roi_genre  = max(genre_prof, key=lambda x: x["avg_roi"])  if genre_prof else {"genre":"N/A","avg_roi":0}
top_gross_genre = genre_prof[0] if genre_prof else {"genre":"N/A"}
top_rated_genre = max(genre_prof, key=lambda x: x["avg_score"]) if genre_prof else {"genre":"N/A","avg_score":0}
most_common_genre = max(genre_prof, key=lambda x: x["count"]) if genre_prof else {"genre":"N/A","count":0}

# ── Audience engagement ───────────────────────────────────────────────────────

engagement_scatter = []
for r in rows:
    s = to_float(r.get("imdb_score",""))
    v = to_int(r.get("num_voted_users",""))
    if not s or not v: continue
    engagement_scatter.append({
        "x":  s,
        "y":  round(v/1000, 1),
        "c":  to_int(r.get("num_critic_for_reviews","")) or 0,
        "t":  r.get("movie_title","").strip(),
        "yr": to_int(r.get("title_year","")) or 0,
    })
engagement_scatter.sort(key=lambda d: -d["y"])
engagement_scatter = engagement_scatter[:2000]  # cap for performance

cr_counts = defaultdict(int)
for r in rows:
    cr = r.get("content_rating","").strip() or "Not Rated"
    cr_counts[cr] += 1
content_ratings = sorted(cr_counts.items(), key=lambda x: -x[1])[:10]

score_edges = [i/2 for i in range(2, 21)]  # 1.0 … 10.0
score_bin_counts = [0]*len(score_edges)
for r in rows:
    s = to_float(r.get("imdb_score",""))
    if s:
        idx = min(int((s-1.0)/0.5), len(score_edges)-1)
        if idx >= 0: score_bin_counts[idx] += 1

all_votes  = [to_int(r.get("num_voted_users","")) for r in rows if to_int(r.get("num_voted_users",""))]
avg_votes  = round(sum(all_votes)/len(all_votes)) if all_votes else 0
all_critic = [to_int(r.get("num_critic_for_reviews","")) for r in rows if to_int(r.get("num_critic_for_reviews",""))]
avg_critic = round(sum(all_critic)/len(all_critic)) if all_critic else 0
top_voted  = max(rows, key=lambda r: to_int(r.get("num_voted_users","")) or 0)
top_voted_title = top_voted.get("movie_title","").strip()
top_voted_n     = to_int(top_voted.get("num_voted_users","")) or 0

# ── Keyword analysis ──────────────────────────────────────────────────────────

kw_map = defaultdict(lambda: {"count":0, "scores":[]})
films_with_kw = 0
for r in rows:
    kws = r.get("plot_keywords","").strip()
    if not kws: continue
    films_with_kw += 1
    s = to_float(r.get("imdb_score",""))
    for kw in kws.split("|"):
        kw = kw.strip()
        if len(kw) > 2:
            kw_map[kw]["count"] += 1
            if s: kw_map[kw]["scores"].append(s)

kw_freq = [[kw, d["count"]] for kw,d in sorted(kw_map.items(), key=lambda x: -x[1]["count"])[:20]]
kw_score_list = [(kw,d) for kw,d in kw_map.items() if d["count"] >= 10]
kw_score_list.sort(key=lambda x: -(sum(x[1]["scores"])/len(x[1]["scores"])) if x[1]["scores"] else 0)
kw_score = [[kw, round(sum(d["scores"])/len(d["scores"]),2), d["count"]] for kw,d in kw_score_list[:20]]

country_counts = defaultdict(int)
for r in rows:
    c = r.get("country","").strip() or "Unknown"
    country_counts[c] += 1
top_countries = [[c,n] for c,n in sorted(country_counts.items(), key=lambda x: -x[1])[:15]]

total_kw = len(kw_map)
top_kw_by_score = kw_score[0][0] if kw_score else "N/A"

# ── Genre-year data (compact, for JS dynamic filter) ─────────────────────────

gyd = []
for r in rows:
    yr_val = to_int(r.get("title_year","")) or 0
    if not yr_val: continue
    genre_val = r.get("genres","").split("|")[0].strip()
    if not genre_val: continue
    sc_val  = to_float(r.get("imdb_score",""))
    gv_val  = to_float(r.get("gross",""))
    bv_val  = to_float(r.get("budget",""))
    cr_val  = r.get("content_rating","").strip() or "Not Rated"
    gyd.append([
        genre_val, yr_val,
        sc_val,
        round(gv_val / 1e6, 1) if gv_val else None,
        round(bv_val / 1e6, 1) if bv_val else None,
        cr_val,
    ])

# ── Pack data ─────────────────────────────────────────────────────────────────

data = {
    "years": years,
    "movies_per_year": movies_per_year,
    "avg_score": avg_score_yr,
    "total_gross": total_gross_yr,
    "avg_budget": avg_budget_yr,
    "genre_series": genre_series,
    "top5_genres": top5_genres,
    "top8_genres": TOP8_GENRES + ([] if "Other" in TOP8_GENRES else ["Other"]),
    "roi_series": roi_series,
    "kpi": {
        "total_films": total_films,
        "year_range": f"{yr_min} – {yr_max}",
        "avg_score": global_avg_score,
        "peak_gross_year": peak_yr,
        "peak_gross_val": int(peak_val),
    },
    "fin_kpi": {
        "avg_roi": avg_roi_global,
        "profitable": profitable_count,
        "total_scatter": len(scatter_data),
        "best_roi_genre": best_roi_genre["genre"],
        "best_roi_val": best_roi_genre["avg_roi"],
        "top_gross_genre": top_gross_genre["genre"],
    },
    "gen_kpi": {
        "total_genres": len(genre_prof),
        "most_common": most_common_genre["genre"],
        "most_common_n": most_common_genre["count"],
        "best_roi": best_roi_genre["genre"],
        "best_roi_val": best_roi_genre["avg_roi"],
        "top_rated": top_rated_genre["genre"],
        "top_rated_val": top_rated_genre["avg_score"],
        "top_gross": top_gross_genre["genre"],
    },
    "eng_kpi": {
        "avg_votes": avg_votes,
        "avg_critic": avg_critic,
        "top_voted": top_voted_title,
        "top_voted_n": top_voted_n,
        "top_rating": content_ratings[0][0] if content_ratings else "N/A",
    },
    "kw_kpi": {
        "total_kw": total_kw,
        "films_with_kw": films_with_kw,
        "top_kw": kw_freq[0][0] if kw_freq else "N/A",
        "top_kw_n": kw_freq[0][1] if kw_freq else 0,
        "top_scored_kw": top_kw_by_score,
    },
    "directors": director_stats,
    "scatter": scatter_data,
    "genre_prof": genre_prof,
    "engagement": engagement_scatter,
    "content_ratings": [[c,n] for c,n in content_ratings],
    "score_bins": [str(b) for b in score_edges],
    "score_bin_counts": score_bin_counts,
    "gyd": gyd,
    "kw_freq": kw_freq,
    "kw_score": kw_score,
    "countries": top_countries,
}

# ── Palette ───────────────────────────────────────────────────────────────────

COLORS = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7","#9c755f"]

# ── HTML ──────────────────────────────────────────────────────────────────────

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Movie Intelligence Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg:      #0f1117;
  --surface: #1a1d27;
  --border:  #2a2d3a;
  --text:    #e2e8f0;
  --muted:   #8892a4;
  --accent:  #4e79a7;
  --accent2: #f28e2b;
}}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
  min-height: 100vh;
  padding: 20px 24px 40px;
}}
header {{ margin-bottom: 16px; }}
header h1 {{ font-size: 20px; font-weight: 600; letter-spacing: -.3px; }}
header p  {{ color: var(--muted); margin-top: 3px; font-size: 12px; }}

/* ── Nav ── */
.page-nav {{
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
  flex-wrap: wrap;
}}
.nav-btn {{
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  font-size: 13px;
  padding: 8px 16px;
  cursor: pointer;
  margin-bottom: -1px;
  white-space: nowrap;
}}
.nav-btn:hover {{ color: var(--text); }}
.nav-btn.active {{ color: var(--text); border-bottom-color: var(--accent); font-weight: 600; }}

/* ── Pages ── */
.page {{ display: none; }}
.page.active {{ display: block; }}

/* ── Year filter ── */
.year-filter {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px 20px 14px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}}
.year-filter-label {{
  font-size: 11px; text-transform: uppercase; letter-spacing: .6px;
  color: var(--muted); white-space: nowrap;
}}
.range-group {{
  display: flex; align-items: center; gap: 10px;
  flex: 1; min-width: 280px;
}}
.range-track-outer {{
  flex: 1;
  display: flex;
  flex-direction: column;
  user-select: none;
  -webkit-user-select: none;
}}
.range-track {{
  position: relative;
  height: 36px;
  display: flex;
  align-items: center;
  overflow: visible;
  margin-top: 20px;
}}
.range-track input[type=range] {{
  position: absolute; width: 100%; height: 4px;
  -webkit-appearance: none; appearance: none;
  background: transparent; pointer-events: none;
  user-select: none; -webkit-user-select: none; -webkit-user-drag: none;
}}
.range-track input[type=range]::-webkit-slider-thumb {{
  -webkit-appearance: none; appearance: none;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--accent); pointer-events: all;
  cursor: grab; border: 2px solid var(--bg); -webkit-user-drag: none;
}}
.range-track input[type=range]:active::-webkit-slider-thumb {{ cursor: grabbing; }}
.range-track input[type=range]::-moz-range-thumb {{
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--accent); pointer-events: all;
  cursor: grab; border: 2px solid var(--bg);
}}
.range-fill {{
  position: absolute; height: 4px;
  background: var(--accent); border-radius: 2px; pointer-events: none;
}}
.range-bg {{
  position: absolute; width: 100%; height: 4px;
  background: var(--border); border-radius: 2px;
}}
.thumb-tip {{
  position: absolute; top: -22px;
  transform: translateX(-50%);
  background: var(--accent); color: #fff;
  font-size: 11px; font-weight: 700;
  padding: 2px 7px; border-radius: 4px;
  pointer-events: none; white-space: nowrap;
  -webkit-user-drag: none; user-select: none; -webkit-user-select: none;
}}
.thumb-tip::after {{
  content: ''; position: absolute; top: 100%; left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent; border-top-color: var(--accent);
}}
.tick-row {{
  position: relative; width: 100%; height: 22px; margin-top: 2px;
}}
.tick {{
  position: absolute; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center;
}}
.tick-mark {{ width: 1px; background: var(--border); }}
.tick.decade .tick-mark {{ height: 9px; background: var(--muted); width: 1.5px; }}
.tick.half .tick-mark   {{ height: 5px; }}
.tick.year .tick-mark   {{ height: 3px; }}
.tick-lbl {{ font-size: 9px; color: var(--muted); margin-top: 2px; white-space: nowrap; }}
.year-filter-apply {{
  background: var(--accent); border: none; border-radius: 6px;
  color: #fff; font-size: 12px; font-weight: 600;
  padding: 7px 18px; cursor: pointer; white-space: nowrap;
  opacity: .9; align-self: flex-start; margin-top: 6px;
}}
.year-filter-apply:hover {{ opacity: 1; }}
.year-filter-apply:disabled {{ opacity: .4; cursor: default; }}
.year-filter-reset {{
  background: none;
  border: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px; padding: 5px 12px; border-radius: 5px;
  cursor: pointer; white-space: nowrap; transition: color .15s, border-color .15s;
}}
.year-filter-reset:hover {{ color: var(--text); border-color: #8892a4; }}
.year-filter-reset:disabled {{ opacity: .35; cursor: default; }}

/* ── KPI row ── */
.kpi-row {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}}
.kpi {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}}
.kpi-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: .6px; color: var(--muted); margin-bottom: 6px; }}
.kpi-value {{ font-size: 22px; font-weight: 700; line-height: 1; }}
.kpi-sub   {{ font-size: 11px; color: var(--muted); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.kpi.accent .kpi-value {{ color: var(--accent); }}
.kpi.pos .kpi-value {{ color: #59a14f; }}
.kpi.warn .kpi-value {{ color: var(--accent2); }}

/* ── Charts grid ── */
.charts-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}
.chart-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px 12px;
}}
.chart-card.wide {{ grid-column: 1 / -1; }}
.chart-title   {{ font-size: 13px; font-weight: 600; margin-bottom: 3px; }}
.chart-caption {{ font-size: 11px; color: var(--muted); margin-bottom: 12px; }}
.chart-wrap                 {{ position: relative; height: 240px; }}
.chart-wrap.tall            {{ height: 300px; }}
.chart-wrap.scatter-h       {{ height: 400px; }}
.chart-wrap.hbar            {{ height: 380px; }}
.chart-wrap.hbar-sm         {{ height: 280px; }}

/* ── Director leaderboard ── */
.section-header {{ display: flex; align-items: baseline; gap: 12px; margin: 28px 0 14px; }}
.section-header h2 {{ font-size: 15px; font-weight: 600; }}
.section-header p  {{ font-size: 12px; color: var(--muted); }}
.dir-controls {{ display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }}
.dir-search {{
  flex: 1; min-width: 180px; max-width: 300px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); font-size: 13px; padding: 7px 12px; outline: none;
}}
.dir-search:focus {{ border-color: var(--accent); }}
.sort-btns {{ display: flex; gap: 6px; }}
.sort-btn {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; color: var(--muted); font-size: 12px; padding: 6px 14px; cursor: pointer;
}}
.sort-btn.active {{ border-color: var(--accent); color: var(--accent); }}
.dir-table-wrap {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; position: relative;
}}
.dir-loading {{
  display: none; position: absolute; inset: 0;
  background: rgba(26,29,39,.75); border-radius: 8px;
  align-items: center; justify-content: center; z-index: 10; gap: 10px;
  font-size: 13px; color: var(--muted);
}}
.dir-loading.visible {{ display: flex; }}
.spinner {{
  width: 16px; height: 16px;
  border: 2px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin .6s linear infinite; flex-shrink: 0;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
table.dir-table {{ width: 100%; border-collapse: collapse; }}
.dir-table th {{
  font-size: 10px; text-transform: uppercase; letter-spacing: .5px;
  color: var(--muted); padding: 10px 14px; text-align: left;
  border-bottom: 1px solid var(--border);
}}
.dir-table th.num {{ text-align: right; }}
.dir-table td {{ padding: 9px 14px; font-size: 13px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
.dir-table td.num {{ text-align: right; color: var(--muted); }}
.dir-table tr.dir-row {{ cursor: pointer; }}
.dir-table tr.dir-row:hover td {{ background: rgba(78,121,167,.06); }}
.dir-table tr.dir-row.expanded td {{ color: var(--accent); }}
.dir-table tr:last-child td {{ border-bottom: none; }}
.rank-num {{ color: var(--muted); font-size: 12px; }}
.score-pill {{
  display: inline-block; background: rgba(242,142,43,.12);
  color: #f28e2b; border-radius: 4px; padding: 2px 7px; font-size: 12px; font-weight: 600;
}}
.best-film {{ color: var(--muted); font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
tr.filmography-row td {{ padding: 0; background: var(--bg); }}
.filmography-inner {{ padding: 10px 18px 14px 40px; border-top: 1px solid var(--border); }}
.filmography-inner table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.filmography-inner th {{
  color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .4px;
  padding: 4px 10px 6px; text-align: left; border-bottom: 1px solid var(--border);
}}
.filmography-inner th.num {{ text-align: right; }}
.filmography-inner td {{ padding: 5px 10px; border-bottom: 1px solid var(--border); color: var(--text); }}
.filmography-inner td.num {{ text-align: right; color: var(--muted); }}
.filmography-inner tr:last-child td {{ border-bottom: none; }}
.no-results {{ padding: 24px; text-align: center; color: var(--muted); font-size: 13px; }}
.dir-pagination {{ display: flex; align-items: center; justify-content: space-between; margin-top: 12px; flex-wrap: wrap; gap: 8px; }}
.pagination-info {{ font-size: 12px; color: var(--muted); }}
.pagination-btns {{ display: flex; gap: 6px; align-items: center; }}
.page-btn {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; color: var(--muted); font-size: 12px; padding: 5px 13px; cursor: pointer; }}
.page-btn:disabled {{ opacity: .35; cursor: default; }}
.page-btn:not(:disabled):hover {{ border-color: var(--accent); color: var(--accent); }}
.page-indicator {{ font-size: 12px; color: var(--text); padding: 0 4px; }}

@media (max-width: 860px) {{
  .kpi-row {{ grid-template-columns: repeat(2,1fr); }}
  .charts-grid {{ grid-template-columns: 1fr; }}
  .chart-card.wide {{ grid-column: 1; }}
  .page-nav {{ gap: 0; }}
  .nav-btn {{ padding: 8px 10px; font-size: 12px; }}
}}
</style>
</head>
<body>

<header>
  <h1>Movie Intelligence Dashboard</h1>
  <p>Source: IMDB movie_metadata.csv &middot; {data['kpi']['year_range']} &middot; {total_films:,} films</p>
</header>

<!-- Year range filter (global) -->
<div class="year-filter">
  <span class="year-filter-label">Year Range</span>
  <div class="range-group">
    <div class="range-track-outer">
      <div class="range-track" id="rangeTrack">
        <div class="range-bg"></div>
        <div class="range-fill" id="rangeFill"></div>
        <span class="thumb-tip" id="tipMin" draggable="false">1916</span>
        <span class="thumb-tip" id="tipMax" draggable="false">2016</span>
        <input type="range" id="yrMin" min="1916" max="2016" value="1916" step="1"/>
        <input type="range" id="yrMax" min="1916" max="2016" value="2016" step="1"/>
      </div>
      <div class="tick-row" id="tickRow"></div>
    </div>
  </div>
  <button class="year-filter-apply" id="applyFilter" disabled>Apply</button>
  <button class="year-filter-reset" id="resetFilter" disabled>Reset</button>
</div>

<!-- Page navigation -->
<nav class="page-nav">
  <button class="nav-btn active" data-page="overview">Overview</button>
  <button class="nav-btn" data-page="financial">Financial Performance</button>
  <button class="nav-btn" data-page="genre">Genre Intelligence</button>
  <button class="nav-btn" data-page="directors">Director &amp; Cast</button>
  <button class="nav-btn" data-page="engagement">Audience Engagement</button>
  <button class="nav-btn" data-page="keywords">Keywords &amp; Reach</button>
</nav>

<!-- ─────────────────────────── PAGE: OVERVIEW ─────────────────────────────── -->
<div class="page active" id="page-overview">
  <div class="kpi-row">
    <div class="kpi"><div class="kpi-label">Total Films</div><div class="kpi-value">{total_films:,}</div><div class="kpi-sub">in dataset</div></div>
    <div class="kpi"><div class="kpi-label">Year Range</div><div class="kpi-value" style="font-size:18px">{data['kpi']['year_range']}</div><div class="kpi-sub">dataset span</div></div>
    <div class="kpi accent"><div class="kpi-label">Avg IMDB Score</div><div class="kpi-value">{global_avg_score}</div><div class="kpi-sub">all films</div></div>
    <div class="kpi"><div class="kpi-label">Peak Gross Year</div><div class="kpi-value" style="font-size:18px">{peak_yr}</div><div class="kpi-sub">${int(peak_val):,}M total gross</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card"><div class="chart-title">Movies Released per Year</div><div class="chart-caption">Film count by release year</div><div class="chart-wrap"><canvas id="cMovies"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Average IMDB Score per Year</div><div class="chart-caption">Mean user rating over time</div><div class="chart-wrap"><canvas id="cScores"></canvas></div></div>
    <div class="chart-card wide"><div class="chart-title">Total Box Office Gross per Year</div><div class="chart-caption">Sum of reported gross revenue (USD millions)</div><div class="chart-wrap tall"><canvas id="cGross"></canvas></div></div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: FINANCIAL ────────────────────────────── -->
<div class="page" id="page-financial">
  <div class="kpi-row">
    <div class="kpi warn"><div class="kpi-label">Avg ROI</div><div class="kpi-value">{avg_roi_global:+.0f}%</div><div class="kpi-sub">gross vs budget</div></div>
    <div class="kpi pos"><div class="kpi-label">Profitable Films</div><div class="kpi-value">{profitable_count:,}</div><div class="kpi-sub">of {len(scatter_data):,} analyzed</div></div>
    <div class="kpi"><div class="kpi-label">Best ROI Genre</div><div class="kpi-value" style="font-size:16px">{best_roi_genre['genre']}</div><div class="kpi-sub">{best_roi_genre['avg_roi']:+.0f}% avg ROI</div></div>
    <div class="kpi accent"><div class="kpi-label">Top Gross Genre</div><div class="kpi-value" style="font-size:16px">{top_gross_genre['genre']}</div><div class="kpi-sub">${top_gross_genre['avg_gross']:.0f}M avg gross</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card wide"><div class="chart-title">Budget vs Gross — Scatter</div><div class="chart-caption">Each dot = one film · colored by genre · hover for title &amp; ROI · dashed line = break-even</div><div class="chart-wrap scatter-h"><canvas id="cScatter"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Average ROI per Year</div><div class="chart-caption">Mean return on investment (gross − budget) ÷ budget × 100</div><div class="chart-wrap"><canvas id="cROI"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Top Genres by Avg Gross</div><div class="chart-caption">Mean reported gross revenue per film (USD millions)</div><div class="chart-wrap hbar-sm"><canvas id="cGenreGross"></canvas></div></div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: GENRE ────────────────────────────────── -->
<div class="page" id="page-genre">
  <div class="kpi-row">
    <div class="kpi"><div class="kpi-label">Genres Analyzed</div><div class="kpi-value">{len(genre_prof)}</div><div class="kpi-sub">with ≥ 5 films</div></div>
    <div class="kpi"><div class="kpi-label">Most Prolific</div><div class="kpi-value" style="font-size:16px">{most_common_genre['genre']}</div><div class="kpi-sub">{most_common_genre['count']:,} films</div></div>
    <div class="kpi pos"><div class="kpi-label">Best ROI Genre</div><div class="kpi-value" style="font-size:16px">{best_roi_genre['genre']}</div><div class="kpi-sub">{best_roi_genre['avg_roi']:+.0f}% avg ROI</div></div>
    <div class="kpi accent"><div class="kpi-label">Highest Rated</div><div class="kpi-value" style="font-size:16px">{top_rated_genre['genre']}</div><div class="kpi-sub">{top_rated_genre['avg_score']} avg score</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card"><div class="chart-title">Genre Profitability (Avg ROI)</div><div class="chart-caption">Average return on investment per genre · all years</div><div class="chart-wrap hbar"><canvas id="cGenreROI"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Genre Avg IMDB Score</div><div class="chart-caption">Mean user rating per genre · all years</div><div class="chart-wrap hbar"><canvas id="cGenreScore"></canvas></div></div>
    <div class="chart-card wide"><div class="chart-title">Genre Trends Over Time</div><div class="chart-caption">Film count by primary genre per year · responds to year filter</div><div class="chart-wrap tall"><canvas id="cGenreTrends"></canvas></div></div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: DIRECTORS ────────────────────────────── -->
<div class="page" id="page-directors">
  <div class="section-header">
    <h2>Director Leaderboard</h2>
    <p>Click a row to see full filmography · stats reflect active year range</p>
  </div>
  <div class="dir-controls">
    <input class="dir-search" id="dirSearch" type="text" placeholder="Search directors..." autocomplete="off"/>
    <div class="sort-btns">
      <button class="sort-btn active" data-sort="gross">Gross</button>
      <button class="sort-btn" data-sort="score">Score</button>
      <button class="sort-btn" data-sort="count">Films</button>
    </div>
  </div>
  <div class="dir-table-wrap">
    <div class="dir-loading" id="dirLoading"><div class="spinner"></div><span>Loading...</span></div>
    <table class="dir-table">
      <thead><tr>
        <th style="width:40px">#</th>
        <th>Director</th>
        <th class="num">Films</th>
        <th class="num">Avg Score</th>
        <th class="num">Total Gross</th>
        <th>Best Film (by score)</th>
      </tr></thead>
      <tbody id="dirTbody"></tbody>
    </table>
  </div>
  <div class="dir-pagination">
    <span class="pagination-info" id="pageInfo"></span>
    <div class="pagination-btns">
      <button class="page-btn" id="pagePrev">&#8592; Prev</button>
      <span class="page-indicator" id="pageIndicator"></span>
      <button class="page-btn" id="pageNext">Next &#8594;</button>
    </div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: ENGAGEMENT ──────────────────────────── -->
<div class="page" id="page-engagement">
  <div class="kpi-row">
    <div class="kpi accent"><div class="kpi-label">Avg Votes / Film</div><div class="kpi-value">{avg_votes:,}</div><div class="kpi-sub">num_voted_users</div></div>
    <div class="kpi"><div class="kpi-label">Avg Critic Reviews</div><div class="kpi-value">{avg_critic:,}</div><div class="kpi-sub">per film</div></div>
    <div class="kpi"><div class="kpi-label">Most Voted Film</div><div class="kpi-value" style="font-size:13px;line-height:1.3">{top_voted_title[:28]}{'…' if len(top_voted_title)>28 else ''}</div><div class="kpi-sub">{top_voted_n:,} votes</div></div>
    <div class="kpi"><div class="kpi-label">Top Content Rating</div><div class="kpi-value" style="font-size:18px">{content_ratings[0][0] if content_ratings else "N/A"}</div><div class="kpi-sub">{content_ratings[0][1] if content_ratings else 0:,} films</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card wide"><div class="chart-title">Engagement vs Rating — Scatter</div><div class="chart-caption">Each dot = one film · X = IMDB score · Y = votes (thousands) · hover for title</div><div class="chart-wrap scatter-h"><canvas id="cEngagement"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">IMDB Score Distribution</div><div class="chart-caption">Number of films per 0.5-point score bucket</div><div class="chart-wrap"><canvas id="cScoreDist"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Content Rating Breakdown</div><div class="chart-caption">Film count by MPAA / content rating</div><div class="chart-wrap hbar-sm"><canvas id="cRating"></canvas></div></div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: KEYWORDS ────────────────────────────── -->
<div class="page" id="page-keywords">
  <div class="kpi-row">
    <div class="kpi"><div class="kpi-label">Unique Keywords</div><div class="kpi-value">{total_kw:,}</div><div class="kpi-sub">across all films</div></div>
    <div class="kpi"><div class="kpi-label">Films with Keywords</div><div class="kpi-value">{films_with_kw:,}</div><div class="kpi-sub">of {total_films:,} total</div></div>
    <div class="kpi accent"><div class="kpi-label">Most Used Keyword</div><div class="kpi-value" style="font-size:15px">{kw_freq[0][0] if kw_freq else 'N/A'}</div><div class="kpi-sub">{kw_freq[0][1] if kw_freq else 0:,} films</div></div>
    <div class="kpi"><div class="kpi-label">Highest Scoring Kw.</div><div class="kpi-value" style="font-size:15px">{top_kw_by_score}</div><div class="kpi-sub">by avg IMDB score</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card"><div class="chart-title">Top 20 Keywords by Frequency</div><div class="chart-caption">Most common plot keywords across dataset</div><div class="chart-wrap hbar"><canvas id="cKwFreq"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Top 20 Keywords by Avg Score</div><div class="chart-caption">Keywords associated with highest-rated films (min 10 films)</div><div class="chart-wrap hbar"><canvas id="cKwScore"></canvas></div></div>
    <div class="chart-card wide"><div class="chart-title">Country Distribution</div><div class="chart-caption">Number of films per country of production</div><div class="chart-wrap hbar-sm"><canvas id="cCountries"></canvas></div></div>
  </div>
</div>

<script>
const D = {json.dumps(data)};
const COLORS = {json.dumps(COLORS)};

// ── Chart defaults ────────────────────────────────────────────────────────────

const DEF = {{
  responsive: true, maintainAspectRatio: false, animation: false,
  plugins: {{
    legend: {{ labels: {{ color:"#8892a4", font:{{ size:11 }} }} }},
    tooltip: {{
      backgroundColor:"#1a1d27", borderColor:"#2a2d3a", borderWidth:1,
      titleColor:"#e2e8f0", bodyColor:"#8892a4",
    }}
  }},
  scales: {{
    x: {{ ticks:{{ color:"#8892a4", font:{{ size:10 }}, maxRotation:45 }}, grid:{{ color:"#2a2d3a" }} }},
    y: {{ ticks:{{ color:"#8892a4", font:{{ size:10 }} }}, grid:{{ color:"#2a2d3a" }} }}
  }}
}};

function merge(a, b) {{
  const r = JSON.parse(JSON.stringify(a));
  for (const k in b) {{
    if (b[k] && typeof b[k]==="object" && !Array.isArray(b[k])) r[k] = merge(r[k]||{{}}, b[k]);
    else r[k] = b[k];
  }}
  return r;
}}

// ── Year filter state ─────────────────────────────────────────────────────────

let activeMin = Math.min(...D.years);
let activeMax = Math.max(...D.years);

function getYearSlice(lo, hi) {{
  const idx = D.years.reduce((a,y,i) => {{ if(y>=lo && y<=hi) a.push(i); return a; }}, []);
  return {{
    labels: idx.map(i => D.years[i]),
    movies: idx.map(i => D.movies_per_year[i]),
    score:  idx.map(i => D.avg_score[i]),
    gross:  idx.map(i => D.total_gross[i]),
    budget: idx.map(i => D.avg_budget[i]),
    roi:    idx.map(i => D.roi_series[i]),
    genres: D.top5_genres.reduce((o,g) => {{ o[g]=idx.map(i=>D.genre_series[g][i]); return o; }}, {{}}),
    avgGross: idx.map(i => {{
      const cnt=D.movies_per_year[i], g=D.total_gross[i];
      return cnt>0&&g!=null ? Math.round(g/cnt*10)/10 : null;
    }})
  }};
}}

// ── Chart references ──────────────────────────────────────────────────────────

const C = {{}};
const INIT = {{}};

// ── Page navigation ───────────────────────────────────────────────────────────

const initPage = {{
  overview: initOverview,
  financial: initFinancial,
  genre: initGenre,
  directors: () => {{ filteredList = buildFilteredList(); renderTable(); }},
  engagement: initEngagement,
  keywords: initKeywords,
}};

function showPage(name) {{
  document.querySelectorAll(".page").forEach(p => p.style.display="none");
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("page-"+name).style.display = "block";
  document.querySelector(`[data-page="${{name}}"]`).classList.add("active");
  if (!INIT[name]) {{ initPage[name](); INIT[name] = true; }}
}}

document.querySelectorAll(".nav-btn").forEach(btn => {{
  btn.addEventListener("click", () => showPage(btn.dataset.page));
}});

// ── Year filter ───────────────────────────────────────────────────────────────

(function() {{
  const yrMin=document.getElementById("yrMin"), yrMax=document.getElementById("yrMax");
  const fill=document.getElementById("rangeFill");
  const tipMin=document.getElementById("tipMin"), tipMax=document.getElementById("tipMax");
  const applyBtn=document.getElementById("applyFilter");
  const resetBtn=document.getElementById("resetFilter");
  const tickRow=document.getElementById("tickRow");
  const TOTAL = 2016-1916;

  for (let yr=1916; yr<=2016; yr++) {{
    const pct=(yr-1916)/TOTAL*100;
    const tick=document.createElement("div");
    const isDec=yr%10===0, isHalf=yr%5===0&&!isDec;
    tick.className="tick "+(isDec?"decade":isHalf?"half":"year");
    tick.style.left=pct+"%";
    const mark=document.createElement("div"); mark.className="tick-mark"; tick.appendChild(mark);
    if (isDec) {{ const lbl=document.createElement("span"); lbl.className="tick-lbl"; lbl.textContent=yr; tick.appendChild(lbl); }}
    tickRow.appendChild(tick);
  }}

  function updateTrack() {{
    const lo=parseInt(yrMin.value), hi=parseInt(yrMax.value);
    const lp=(lo-1916)/TOTAL*100, rp=(hi-1916)/TOTAL*100;
    fill.style.left=lp+"%"; fill.style.width=(rp-lp)+"%";
    tipMin.textContent=lo; tipMax.textContent=hi;
    tipMin.style.left=lp+"%"; tipMax.style.left=rp+"%";
    tipMin.style.opacity=(lo===hi)?"0":"1";
    applyBtn.disabled=(lo===activeMin && hi===activeMax);
    resetBtn.disabled=(lo===1916 && hi===2016);
  }}

  yrMin.addEventListener("input", () => {{ if(parseInt(yrMin.value)>parseInt(yrMax.value)) yrMin.value=yrMax.value; updateTrack(); }});
  yrMax.addEventListener("input", () => {{ if(parseInt(yrMax.value)<parseInt(yrMin.value)) yrMax.value=yrMin.value; updateTrack(); }});

  applyBtn.addEventListener("click", () => {{
    const lo=parseInt(yrMin.value), hi=parseInt(yrMax.value);
    applyBtn.disabled=true;
    applyYearFilter(lo, hi);
  }});

  resetBtn.addEventListener("click", () => {{
    yrMin.value=1916; yrMax.value=2016;
    updateTrack();
    applyYearFilter(1916, 2016);
  }});

  updateTrack();
}})();

function applyYearFilter(lo, hi) {{
  activeMin=lo; activeMax=hi;
  const s = getYearSlice(lo, hi);
  const gp = getGenreProf(lo, hi);

  if (INIT.overview) {{
    C.movies.data.labels=s.labels;
    C.movies.data.datasets[0].data=s.movies;
    C.movies.data.datasets[1].data=rollingAvg(s.movies);
    C.movies.update();
    C.scores.data.labels=s.labels; C.scores.data.datasets[0].data=s.score;  C.scores.update();
    C.gross.data.labels=s.labels;  C.gross.data.datasets[0].data=s.gross;   C.gross.update();
  }}
  if (INIT.financial) {{
    D.top8_genres.forEach((g,i) => {{
      C.scatter.data.datasets[i].data = D.scatter
        .filter(d => d.g===g && d.yr>=lo && d.yr<=hi)
        .map(d => ({{x:d.x, y:d.y, t:d.t, r:d.r}}));
    }});
    C.scatter.update();
    C.roi.data.labels=s.labels; C.roi.data.datasets[0].data=s.roi; C.roi.update();
    // Genre avg gross
    const gpG = [...gp].sort((a,b)=>b.avg_gross-a.avg_gross).slice(0,12);
    const mgMax = gpG[0]?.avg_gross || 1;
    C.genreGross.data.labels = gpG.map(d=>d.genre);
    C.genreGross.data.datasets[0].data = gpG.map(d=>d.avg_gross);
    C.genreGross.data.datasets[0].backgroundColor = gpG.map(d=>`rgba(78,121,167,${{(0.4+0.55*(d.avg_gross/mgMax)).toFixed(2)}})`);
    C.genreGross.update();
  }}
  if (INIT.genre) {{
    // Genre trends
    D.top5_genres.forEach((g,i) => {{ C.genreTrends.data.datasets[i].data=s.genres[g]; }});
    C.genreTrends.data.labels=s.labels; C.genreTrends.update();
    // Genre ROI
    const gpR = [...gp].sort((a,b)=>b.avg_roi-a.avg_roi).slice(0,15);
    const rMax = Math.max(...gpR.map(d=>Math.abs(d.avg_roi)),1);
    C.genreROI.data.labels = gpR.map(d=>d.genre);
    C.genreROI.data.datasets[0].data = gpR.map(d=>d.avg_roi);
    C.genreROI.data.datasets[0].backgroundColor = gpR.map(d => {{
      const a = (0.45+0.45*(Math.abs(d.avg_roi)/rMax)).toFixed(2);
      return d.avg_roi>=0 ? `rgba(89,161,79,${{a}})` : `rgba(225,87,89,${{a}})`;
    }});
    C.genreROI.update();
    // Genre score
    const gpS = [...gp].sort((a,b)=>b.avg_score-a.avg_score).slice(0,15);
    C.genreScore.data.labels = gpS.map(d=>d.genre);
    C.genreScore.data.datasets[0].data = gpS.map(d=>d.avg_score);
    C.genreScore.data.datasets[0].backgroundColor = gpS.map(d=>scoreColor(d.avg_score, 0.8));
    C.genreScore.update();
  }}
  if (INIT.engagement) {{
    const ep = engPts(lo, hi);
    C.engagement.data.datasets[0].data = ep;
    C.engagement.data.datasets[0].backgroundColor = ep.map(p=>p._c);
    C.engagement.update();
    // Score distribution
    const sd = getScoreDist(lo, hi);
    C.scoreDist.data.datasets[0].data = sd;
    C.scoreDist.update();
    // Content rating doughnut
    const cr = getContentRatings(lo, hi);
    C.contentRating.data.labels = cr.map(d=>d[0]);
    C.contentRating.data.datasets[0].data = cr.map(d=>d[1]);
    C.contentRating.update();
  }}
  filteredList = buildFilteredList(); currentPage=0; renderTable();
}}

// ── Visual helpers ────────────────────────────────────────────────────────────

function mkGrad(id, topColor, botColor) {{
  const el = document.getElementById(id);
  if (!el) return topColor;
  const ctx2 = el.getContext('2d');
  const h = el.closest('.chart-wrap')?.offsetHeight || 240;
  const g = ctx2.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, topColor);
  g.addColorStop(1, botColor);
  return g;
}}

function rollingAvg(arr, w=5) {{
  return arr.map((_,i) => {{
    const sl = arr.slice(Math.max(0,i-w+1),i+1).filter(x=>x!=null);
    return sl.length ? Math.round(sl.reduce((a,b)=>a+b,0)/sl.length*10)/10 : null;
  }});
}}

function scoreColor(s, alpha=0.55) {{
  if (s >= 7.5) return `rgba(89,161,79,${{alpha}})`;
  if (s >= 6.5) return `rgba(78,121,167,${{alpha}})`;
  if (s >= 5.0) return `rgba(237,201,72,${{alpha}})`;
  return `rgba(225,87,89,${{alpha}})`;
}}

// ── Dynamic aggregation helpers (use D.gyd for year-aware genre/score stats) ──

function getGenreProf(lo, hi) {{
  const gmap = {{}};
  D.gyd.filter(d => d[1]>=lo && d[1]<=hi).forEach(([genre, , sc, gross, budget]) => {{
    if (!gmap[genre]) gmap[genre] = {{gross:[],roi:[],score:[]}};
    if (gross != null) gmap[genre].gross.push(gross);
    if (sc   != null) gmap[genre].score.push(sc);
    if (gross != null && budget != null && budget > 0)
      gmap[genre].roi.push((gross-budget)/budget*100);
  }});
  const avg = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;
  return Object.entries(gmap)
    .filter(([,v]) => v.score.length>=3 || v.gross.length>=3)
    .map(([genre,v]) => ({{
      genre,
      avg_gross: Math.round(avg(v.gross)*10)/10,
      avg_roi:   Math.round(avg(v.roi)*10)/10,
      avg_score: Math.round(avg(v.score)*100)/100,
      count: Math.max(v.gross.length, v.score.length),
    }}));
}}

function getScoreDist(lo, hi) {{
  const bins = D.score_bins.length;
  const counts = new Array(bins).fill(0);
  D.gyd.filter(d => d[1]>=lo && d[1]<=hi && d[2]!=null).forEach(([,,sc]) => {{
    const idx = Math.min(Math.floor((sc-1.0)/0.5), bins-1);
    if (idx>=0) counts[idx]++;
  }});
  return counts;
}}

function getContentRatings(lo, hi) {{
  const cmap = {{}};
  D.gyd.filter(d => d[1]>=lo && d[1]<=hi).forEach(([,,,,, cr]) => {{
    cmap[cr] = (cmap[cr]||0) + 1;
  }});
  return Object.entries(cmap).sort((a,b)=>b[1]-a[1]).slice(0,8);
}}

// inline value-label plugin
const valLabelPlugin = {{
  id:'valLabel',
  afterDatasetsDraw(chart, _, opts) {{
    if (!opts || !opts.show) return;
    const {{ctx:cx}} = chart;
    const isH = chart.options.indexAxis==='y';
    chart.data.datasets.forEach((ds,di) => {{
      if (ds._noLabel) return;
      chart.getDatasetMeta(di).data.forEach((bar,ji) => {{
        const v = ds.data[ji]; if (v==null) return;
        const lbl = opts.fmt ? opts.fmt(v) : String(v);
        cx.save();
        cx.fillStyle='#8892a4'; cx.font='10px sans-serif';
        if (isH) {{ cx.textAlign='left'; cx.textBaseline='middle'; cx.fillText(lbl, bar.x+5, bar.y); }}
        else      {{ cx.textAlign='center'; cx.textBaseline='bottom'; cx.fillText(lbl, bar.x, bar.y-4); }}
        cx.restore();
      }});
    }});
  }}
}};
Chart.register(valLabelPlugin);

// ── OVERVIEW ─────────────────────────────────────────────────────────────────

function initOverview() {{
  const s = getYearSlice(activeMin, activeMax);

  // Movies/year — bars + rolling-average line
  C.movies = new Chart(document.getElementById("cMovies"), {{
    type:"bar",
    data:{{ labels:s.labels, datasets:[
      {{ type:"bar",  label:"Films released", data:s.movies, backgroundColor:"rgba(78,121,167,.65)", borderRadius:4, order:2 }},
      {{ type:"line", label:"5-yr avg",        data:rollingAvg(s.movies), borderColor:"#f28e2b", borderWidth:2, pointRadius:0, tension:.5, fill:false, order:1, _noLabel:true }}
    ] }},
    options:merge(DEF, {{
      plugins:{{ legend:{{ display:true, position:"top", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12 }} }} }},
      scales:{{ y:{{ title:{{ display:true, text:"Films", color:"#8892a4", font:{{ size:11 }} }} }} }}
    }})
  }});

  // Avg IMDB score — gradient area
  C.scores = new Chart(document.getElementById("cScores"), {{
    type:"line",
    data:{{ labels:s.labels, datasets:[{{
      label:"Avg IMDB score", data:s.score,
      borderColor:"#f28e2b", borderWidth:2.5,
      backgroundColor: mkGrad("cScores","rgba(242,142,43,.35)","rgba(242,142,43,0)"),
      fill:true, tension:.4, pointRadius:3, pointHoverRadius:7,
      pointBackgroundColor:"#f28e2b", pointBorderColor:"#0f1117", pointBorderWidth:2,
    }}] }},
    options:merge(DEF, {{
      plugins:{{ legend:{{ display:false }} }},
      scales:{{ y:{{ title:{{ display:true, text:"IMDB score", color:"#8892a4", font:{{ size:11 }} }}, min:5, max:8 }} }}
    }})
  }});

  // Box office gross — gradient area + taller
  C.gross = new Chart(document.getElementById("cGross"), {{
    type:"line",
    data:{{ labels:s.labels, datasets:[{{
      label:"Total gross (USD M)", data:s.gross,
      borderColor:"#59a14f", borderWidth:2.5,
      backgroundColor: mkGrad("cGross","rgba(89,161,79,.4)","rgba(89,161,79,0)"),
      fill:true, tension:.3, pointRadius:3, pointHoverRadius:7,
      pointBackgroundColor:"#59a14f", pointBorderColor:"#0f1117", pointBorderWidth:2,
    }}] }},
    options:merge(DEF, {{
      plugins:{{ legend:{{ display:false }} }},
      scales:{{ y:{{ title:{{ display:true, text:"Gross (USD millions)", color:"#8892a4", font:{{ size:11 }} }},
        ticks:{{ callback: v => `$${{Math.round(v/1000*10)/10}}B` }} }} }}
    }})
  }});
}}

// ── FINANCIAL ────────────────────────────────────────────────────────────────

function initFinancial() {{
  const GENRES = D.top8_genres;
  const maxBudget = Math.max(...D.scatter.map(d=>d.x), 400);

  // Scatter: budget vs gross
  const scatterDatasets = GENRES.map((g,i) => ({{
    label: g,
    type: "scatter",
    data: D.scatter
      .filter(d => d.g===g && d.yr>=activeMin && d.yr<=activeMax)
      .map(d => ({{x:d.x, y:d.y, t:d.t, r:d.r}})),
    backgroundColor: COLORS[i]+"99",
    pointRadius: 4,
    pointHoverRadius: 6,
  }}));
  // break-even line
  scatterDatasets.push({{
    label: "Break-even",
    type: "line",
    data: [{{x:0,y:0}},{{x:maxBudget,y:maxBudget}}],
    borderColor:"#3a3d4a", borderWidth:1.5,
    borderDash:[6,4], pointRadius:0, fill:false,
  }});

  C.scatter = new Chart(document.getElementById("cScatter"), {{
    type:"scatter",
    data:{{ datasets: scatterDatasets }},
    options: merge(DEF, {{
      plugins: {{
        legend: {{ position:"bottom", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12 }} }},
        tooltip: {{
          backgroundColor:"#1a1d27", borderColor:"#2a2d3a", borderWidth:1,
          titleColor:"#e2e8f0", bodyColor:"#8892a4",
          callbacks: {{
            label: ctx => {{
              if (!ctx.raw.t) return `Break-even`;
              return `${{ctx.raw.t}} · Budget: $${{ctx.raw.x}}M · Gross: $${{ctx.raw.y}}M · ROI: ${{ctx.raw.r}}%`;
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ title:{{ display:true, text:"Budget (USD millions)", color:"#8892a4", font:{{ size:11 }} }}, ticks:{{ color:"#8892a4", font:{{ size:10 }} }}, grid:{{ color:"#2a2d3a" }} }},
        y: {{ title:{{ display:true, text:"Gross (USD millions)", color:"#8892a4", font:{{ size:11 }} }}, ticks:{{ color:"#8892a4", font:{{ size:10 }} }}, grid:{{ color:"#2a2d3a" }} }}
      }}
    }})
  }});

  // ROI by year — gradient fill, zero line, color above/below
  const s = getYearSlice(activeMin, activeMax);
  C.roi = new Chart(document.getElementById("cROI"), {{
    type:"line",
    data:{{ labels:s.labels, datasets:[{{
      label:"Avg ROI %", data:s.roi,
      borderColor:"#edc948", borderWidth:2.5,
      backgroundColor: mkGrad("cROI","rgba(237,201,72,.35)","rgba(237,201,72,0)"),
      fill:true, tension:.35, pointRadius:3, pointHoverRadius:7,
      pointBackgroundColor:"#edc948", pointBorderColor:"#0f1117", pointBorderWidth:2,
    }}] }},
    options:merge(DEF, {{
      plugins:{{ legend:{{ display:false }} }},
      scales:{{
        y:{{
          title:{{ display:true, text:"ROI (%)", color:"#8892a4", font:{{ size:11 }} }},
          ticks:{{ callback: v => v+'%' }},
          grid:{{ color: ctx => ctx.tick.value===0 ? "#4a4d5a" : "#2a2d3a" }}
        }}
      }}
    }})
  }});

  // Genre avg gross — opacity scaled to value
  const gpSorted = [...D.genre_prof].sort((a,b)=>b.avg_gross-a.avg_gross).slice(0,12);
  const maxGross = gpSorted[0]?.avg_gross || 1;
  C.genreGross = new Chart(document.getElementById("cGenreGross"), {{
    type:"bar",
    data:{{ labels:gpSorted.map(d=>d.genre), datasets:[{{
      label:"Avg Gross (M)", data:gpSorted.map(d=>d.avg_gross),
      backgroundColor: gpSorted.map(d => `rgba(78,121,167,${{(0.4 + 0.55*(d.avg_gross/maxGross)).toFixed(2)}})` ),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{ legend:{{ display:false }}, valLabel:{{ show:true, fmt:v=>`$${{Math.round(v)}}M` }} }},
      scales:{{ x:{{ title:{{ display:true, text:"USD millions", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:11 }} }} }} }}
    }})
  }});
}}

// ── GENRE ────────────────────────────────────────────────────────────────────

function initGenre() {{
  // Genre ROI — green/red bars + value labels
  const gpROI = [...D.genre_prof].sort((a,b)=>b.avg_roi-a.avg_roi).slice(0,15);
  const roiMax = Math.max(...gpROI.map(d=>Math.abs(d.avg_roi)),1);
  C.genreROI = new Chart(document.getElementById("cGenreROI"), {{
    type:"bar",
    data:{{ labels:gpROI.map(d=>d.genre), datasets:[{{
      label:"Avg ROI %",
      data:gpROI.map(d=>d.avg_roi),
      backgroundColor: gpROI.map(d => {{
        const alpha = 0.45 + 0.45*(Math.abs(d.avg_roi)/roiMax);
        return d.avg_roi>=0 ? `rgba(89,161,79,${{alpha.toFixed(2)}})` : `rgba(225,87,89,${{alpha.toFixed(2)}})`;
      }}),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true, fmt:v=>`${{Math.round(v)}}%` }}
      }},
      scales:{{
        x:{{ title:{{ display:true, text:"Return on Investment (%)", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0, callback:v=>v+'%' }}, grid:{{ color: ctx=>ctx.tick.value===0?"#4a4d5a":"#2a2d3a" }} }},
        y:{{ ticks:{{ font:{{ size:11 }} }} }}
      }}
    }})
  }});

  // Genre avg score — colored by score bucket
  const gpScore = [...D.genre_prof].sort((a,b)=>b.avg_score-a.avg_score).slice(0,15);
  C.genreScore = new Chart(document.getElementById("cGenreScore"), {{
    type:"bar",
    data:{{ labels:gpScore.map(d=>d.genre), datasets:[{{
      label:"Avg IMDB Score", data:gpScore.map(d=>d.avg_score),
      backgroundColor: gpScore.map(d=>scoreColor(d.avg_score, 0.8)),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true, fmt:v=>v.toFixed(1) }}
      }},
      scales:{{ x:{{ min:0, max:9, title:{{ display:true, text:"IMDB Score", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:11 }} }} }} }}
    }})
  }});

  // Genre trends — filled area lines
  const s = getYearSlice(activeMin, activeMax);
  C.genreTrends = new Chart(document.getElementById("cGenreTrends"), {{
    type:"line",
    data:{{ labels:s.labels, datasets:D.top5_genres.map((g,i)=>({{
      label:g, data:s.genres[g],
      borderColor:COLORS[i],
      backgroundColor: COLORS[i]+'22',
      fill:true, tension:.35, pointRadius:1.5, pointHoverRadius:6, borderWidth:2,
    }})) }},
    options:merge(DEF, {{
      plugins:{{ legend:{{ display:true, position:"bottom", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12 }} }} }},
      scales:{{ y:{{ title:{{ display:true, text:"Films per year", color:"#8892a4", font:{{ size:11 }} }}, stacked:false }} }}
    }})
  }});
}}

// ── ENGAGEMENT ───────────────────────────────────────────────────────────────

function engPts(lo, hi) {{
  return D.engagement
    .filter(d=>d.yr>=lo&&d.yr<=hi)
    .map(d => ({{ x:d.x, y:d.y, t:d.t, _c:scoreColor(d.x,0.6) }}));
}}

function initEngagement() {{
  // Score vs votes — per-point color by IMDB score
  const pts = engPts(activeMin, activeMax);
  C.engagement = new Chart(document.getElementById("cEngagement"), {{
    type:"scatter",
    data:{{ datasets:[{{
      label:"Films", data:pts,
      backgroundColor: pts.map(p=>p._c),
      pointRadius:3.5, pointHoverRadius:8,
    }}] }},
    options:merge(DEF, {{
      plugins:{{
        legend:{{ display:false }},
        tooltip:{{
          backgroundColor:"#1a1d27", borderColor:"#2a2d3a", borderWidth:1,
          titleColor:"#e2e8f0", bodyColor:"#8892a4",
          callbacks:{{
            label: ctx => `${{ctx.raw.t}} · Score: ${{ctx.raw.x}} · Votes: ${{(ctx.raw.y*1000).toLocaleString()}}`,
            title: ()=>''
          }}
        }}
      }},
      scales:{{
        x:{{ title:{{ display:true, text:"IMDB Score  ( green ≥ 7.5 · blue 6.5–7.5 · yellow 5–6.5 · red < 5 )", color:"#8892a4", font:{{ size:10 }} }}, min:1, max:10 }},
        y:{{ title:{{ display:true, text:"Votes (thousands)", color:"#8892a4", font:{{ size:11 }} }} }}
      }}
    }})
  }});

  // Score distribution — color each bar by bucket
  const binColors = D.score_bins.map(b=>scoreColor(parseFloat(b)+0.5, 0.8));
  C.scoreDist = new Chart(document.getElementById("cScoreDist"), {{
    type:"bar",
    data:{{ labels:D.score_bins, datasets:[{{
      label:"Films", data:D.score_bin_counts,
      backgroundColor: binColors, borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true }}
      }},
      scales:{{
        x:{{ title:{{ display:true, text:"IMDB Score", color:"#8892a4", font:{{ size:11 }} }}, ticks:{{ maxRotation:0 }} }},
        y:{{ title:{{ display:true, text:"Film count", color:"#8892a4", font:{{ size:11 }} }} }}
      }}
    }})
  }});

  // Content ratings — doughnut
  const cr = D.content_ratings.slice(0,8);
  const crPalette = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"];
  C.contentRating = new Chart(document.getElementById("cRating"), {{
    type:"doughnut",
    data:{{ labels:cr.map(d=>d[0]), datasets:[{{
      data:cr.map(d=>d[1]),
      backgroundColor:crPalette,
      borderColor:"#0f1117", borderWidth:3,
      hoverOffset:12,
    }}] }},
    options:merge(DEF, {{
      cutout:"62%",
      plugins:{{
        legend:{{ display:true, position:"right", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12, padding:10 }} }},
        tooltip:{{
          backgroundColor:"#1a1d27", borderColor:"#2a2d3a", borderWidth:1,
          bodyColor:"#e2e8f0",
          callbacks:{{
            label: ctx => ` ${{ctx.label}} — ${{ctx.raw}} films (${{Math.round(ctx.raw/cr.reduce((s,d)=>s+d[1],0)*100)}}%)`
          }}
        }}
      }}
    }})
  }});
}}

// ── KEYWORDS ─────────────────────────────────────────────────────────────────

function initKeywords() {{
  // Keyword frequency — fading blue bars by rank
  const kwN = D.kw_freq.length;
  C.kwFreq = new Chart(document.getElementById("cKwFreq"), {{
    type:"bar",
    data:{{ labels:D.kw_freq.map(d=>d[0]), datasets:[{{
      label:"Appearances", data:D.kw_freq.map(d=>d[1]),
      backgroundColor: D.kw_freq.map((_,i)=>`rgba(78,121,167,${{(0.9-0.5*i/kwN).toFixed(2)}})` ),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{ legend:{{ display:false }}, valLabel:{{ show:true }} }},
      scales:{{ x:{{ title:{{ display:true, text:"Film count", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }}
    }})
  }});

  // Keyword score — colored by score bucket
  C.kwScore = new Chart(document.getElementById("cKwScore"), {{
    type:"bar",
    data:{{ labels:D.kw_score.map(d=>d[0]), datasets:[{{
      label:"Avg IMDB Score", data:D.kw_score.map(d=>d[1]),
      backgroundColor: D.kw_score.map(d=>scoreColor(d[1], 0.85)),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{ legend:{{ display:false }}, valLabel:{{ show:true, fmt:v=>v.toFixed(1) }} }},
      scales:{{ x:{{ min:0, max:9, title:{{ display:true, text:"IMDB Score", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }}
    }})
  }});

  // Country production — fading teal bars
  const ctN = D.countries.length;
  C.countries = new Chart(document.getElementById("cCountries"), {{
    type:"bar",
    data:{{ labels:D.countries.map(d=>d[0]), datasets:[{{
      label:"Films", data:D.countries.map(d=>d[1]),
      backgroundColor: D.countries.map((_,i)=>`rgba(89,161,79,${{(0.9-0.5*i/ctN).toFixed(2)}})` ),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{ legend:{{ display:false }}, valLabel:{{ show:true }} }},
      scales:{{ x:{{ title:{{ display:true, text:"Film count", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }}
    }})
  }});
}}

// ── DIRECTOR LEADERBOARD ─────────────────────────────────────────────────────

const PAGE_SIZE = 25;
let sortKey = "gross", filterText = "", currentPage = 0;
let expandedRow = null, filteredList = [];

function fmtGross(v) {{
  if (!v) return "—";
  return v>=1000 ? `$${{(v/1000).toFixed(1)}}B` : `$${{v.toFixed(0)}}M`;
}}

function buildFilteredList() {{
  let list = D.directors.map(d => {{
    const films = d.films.filter(f => f.y>=activeMin && f.y<=activeMax);
    if (!films.length) return null;
    const sc = films.map(f=>f.s).filter(Boolean);
    const gr = films.map(f=>f.g).filter(v=>v!=null);
    const best = films.reduce((a,b)=>((b.s||0)>(a.s||0)?b:a));
    return {{ name:d.name, count:films.length, avg_score:sc.length?Math.round(sc.reduce((a,b)=>a+b,0)/sc.length*100)/100:null, total_gross:gr.length?Math.round(gr.reduce((a,b)=>a+b,0)*10)/10:0, best:best.t, films }};
  }}).filter(d => d && d.name.toLowerCase().includes(filterText));

  if (sortKey==="gross") list.sort((a,b)=>(b.total_gross||0)-(a.total_gross||0));
  if (sortKey==="score") list.sort((a,b)=>(b.avg_score||0)-(a.avg_score||0));
  if (sortKey==="count") list.sort((a,b)=>b.count-a.count);
  return list;
}}

function showLoading(then) {{
  const ov=document.getElementById("dirLoading"); ov.classList.add("visible");
  requestAnimationFrame(()=>requestAnimationFrame(()=>{{ then(); ov.classList.remove("visible"); }}));
}}

function renderTable() {{
  const tbody=document.getElementById("dirTbody");
  const pInfo=document.getElementById("pageInfo"), pInd=document.getElementById("pageIndicator");
  const btnPrev=document.getElementById("pagePrev"), btnNext=document.getElementById("pageNext");
  tbody.innerHTML=""; expandedRow=null;

  const totalPages=Math.max(1,Math.ceil(filteredList.length/PAGE_SIZE));
  if (currentPage>=totalPages) currentPage=totalPages-1;
  const start=currentPage*PAGE_SIZE;
  const items=filteredList.slice(start, start+PAGE_SIZE);

  pInd.textContent=`Page ${{currentPage+1}} of ${{totalPages}}`;
  pInfo.textContent=filteredList.length===0?"No directors found":`Showing ${{start+1}}–${{Math.min(start+PAGE_SIZE,filteredList.length)}} of ${{filteredList.length}} directors`;
  btnPrev.disabled=currentPage===0; btnNext.disabled=currentPage>=totalPages-1;

  if (!filteredList.length) {{ tbody.innerHTML=`<tr><td colspan="6" class="no-results">No directors match.</td></tr>`; return; }}

  items.forEach((d,i) => {{
    const tr=document.createElement("tr"); tr.className="dir-row";
    tr.innerHTML=`<td><span class="rank-num">${{start+i+1}}</span></td><td><strong>${{d.name}}</strong></td><td class="num">${{d.count}}</td><td class="num">${{d.avg_score!=null?`<span class="score-pill">${{d.avg_score}}</span>`:"—"}}</td><td class="num">${{fmtGross(d.total_gross)}}</td><td><span class="best-film" title="${{d.best}}">${{d.best}}</span></td>`;

    tr.addEventListener("click", () => {{
      if (expandedRow&&expandedRow.dataRow!==tr) {{ expandedRow.filmRow.remove(); expandedRow.dataRow.classList.remove("expanded"); expandedRow=null; }}
      if (expandedRow&&expandedRow.dataRow===tr) {{ expandedRow.filmRow.remove(); tr.classList.remove("expanded"); expandedRow=null; return; }}
      tr.classList.add("expanded");
      const filmTr=document.createElement("tr"); filmTr.className="filmography-row";
      filmTr.innerHTML=`<td colspan="6"><div class="filmography-inner"><table><thead><tr><th>Title</th><th class="num">Year</th><th class="num">Score</th><th class="num">Gross</th></tr></thead><tbody>${{d.films.map(f=>`<tr><td>${{f.t}}</td><td class="num">${{f.y||"—"}}</td><td class="num">${{f.s??"—"}}</td><td class="num">${{f.g!=null?fmtGross(f.g):"—"}}</td></tr>`).join("")}}</tbody></table></div></td>`;
      tr.after(filmTr); expandedRow={{dataRow:tr,filmRow:filmTr}};
    }});
    tbody.appendChild(tr);
  }});
}}

function refresh() {{ showLoading(()=>{{ filteredList=buildFilteredList(); renderTable(); }}); }}

let searchTimer;
document.getElementById("dirSearch").addEventListener("input", e => {{ filterText=e.target.value.toLowerCase().trim(); currentPage=0; clearTimeout(searchTimer); searchTimer=setTimeout(refresh,80); }});
document.querySelectorAll(".sort-btn").forEach(btn => {{ btn.addEventListener("click",()=>{{ document.querySelectorAll(".sort-btn").forEach(b=>b.classList.remove("active")); btn.classList.add("active"); sortKey=btn.dataset.sort; currentPage=0; refresh(); }}); }});
document.getElementById("pagePrev").addEventListener("click",()=>{{ if(currentPage>0){{currentPage--;refresh();}} }});
document.getElementById("pageNext").addEventListener("click",()=>{{ const t=Math.ceil(filteredList.length/PAGE_SIZE); if(currentPage<t-1){{currentPage++;refresh();}} }});

// ── Boot ──────────────────────────────────────────────────────────────────────

showPage("overview");
INIT.overview = true;
filteredList = buildFilteredList(); renderTable();

</script>
</body>
</html>
"""

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard written → {OUT_PATH}")
print(f"  Years: {years[0]}–{years[-1]} ({len(years)} years)")
print(f"  Scatter points: {len(scatter_data)}")
print(f"  Engagement points: {len(engagement_scatter)}")
print(f"  Genre profiles: {len(genre_prof)}")
print(f"  Keywords: {total_kw:,}  |  Countries: {len(top_countries)}")
print(f"  Directors: {len(director_stats):,}")
