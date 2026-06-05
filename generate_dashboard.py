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

# ── Financial data validation (currency sanity) ───────────────────────────────
# Rules based on expert recommendation:
#   1. Budget > $400M USD → almost certainly an unconverted foreign currency
#   2. Gross  > $3B  USD → above the all-time box-office record; impossible
#   3. For films with budget > $1M, gross/budget ratio < 0.005 or > 500 → unit mismatch
#      (e.g. Princess Mononoke: ¥2.35B budget read as $2.35B → ratio ≈ 0.0009)

MAX_BUDGET_USD = 400_000_000    # $400M hard ceiling
MAX_GROSS_USD  = 3_000_000_000  # $3B  hard ceiling (above Avatar's record)
MIN_ROI_RATIO  = 0.005          # below 0.5% recovery at scale = bad units
MAX_ROI_RATIO  = 500            # above 500x at non-trivial budget = bad units

_currency_flags = []   # collect titles flagged for reporting

def is_valid_usd(b, g, title=""):
    """Return True if budget and/or gross are plausible USD values."""
    reason = None
    if b and b > MAX_BUDGET_USD:
        reason = f"budget ${b/1e6:.0f}M > $400M ceiling"
    elif g and g > MAX_GROSS_USD:
        reason = f"gross ${g/1e6:.0f}M > $3B ceiling"
    elif b and g and b > 1_000_000:
        ratio = g / b
        if ratio < MIN_ROI_RATIO:
            reason = f"gross/budget ratio {ratio:.5f} < 0.005 (likely foreign currency)"
        elif ratio > MAX_ROI_RATIO:
            reason = f"gross/budget ratio {ratio:.0f}x > 500x (likely foreign currency)"
    if reason:
        _currency_flags.append(f"  FLAGGED [{title}]: {reason}")
        return False
    return True

def clean_b(b, title=""):
    """Return budget if valid USD, else None."""
    if b and b > MAX_BUDGET_USD:
        _currency_flags.append(f"  FLAGGED [{title}]: budget ${b/1e6:.0f}M > $400M ceiling")
        return None
    return b

def clean_g(g, title=""):
    """Return gross if valid USD, else None."""
    if g and g > MAX_GROSS_USD:
        _currency_flags.append(f"  FLAGGED [{title}]: gross ${g/1e6:.0f}M > $3B ceiling")
        return None
    return g

def is_us_film(r):
    """Return True if the primary production country is USA.
    Non-US films have budgets in local currency while gross is US domestic (USD),
    making budget/ROI comparisons meaningless across currencies."""
    c = r.get("country", "").strip()
    return c == "USA" or c.startswith("USA|") or c.startswith("USA,")

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
    title_yr = r.get("movie_title", "").strip()
    g = clean_g(to_float(r.get("gross", "")), title_yr)
    if g: year_gross[yr] += g / 1e6
    # Budget only from US films — non-US budgets are in local currency
    if is_us_film(r):
        b = clean_b(to_float(r.get("budget", "")), title_yr)
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

# ── Actor aggregation ─────────────────────────────────────────────────────────

actor_map = defaultdict(list)
for r in rows:
    title = r.get("movie_title", "").strip()
    yr    = to_int(r.get("title_year", "")) or 0
    sc    = to_float(r.get("imdb_score", ""))
    gv    = clean_g(to_float(r.get("gross", "")), title)
    genre = r.get("genres", "").split("|")[0].strip() or "Other"
    for role_num in (1, 2, 3):
        name = r.get(f"actor_{role_num}_name", "").strip()
        if not name:
            continue
        actor_map[name].append({
            "t":     title,
            "y":     yr,
            "s":     sc,
            "g":     round(gv / 1e6, 1) if gv else None,
            "r":     role_num,
            "genre": genre,
        })

actor_stats = []
for name, films in actor_map.items():
    if len(films) < 3:
        continue
    actor_stats.append({
        "name":  name,
        "films": sorted(films, key=lambda f: f["y"]),
    })
actor_stats.sort(key=lambda a: a["name"])

# ── Film list (individual films leaderboard) ──────────────────────────────────

films_list = []
for r in rows:
    title = r.get("movie_title", "").strip()
    yr    = to_int(r.get("title_year", "")) or 0
    sc    = to_float(r.get("imdb_score", ""))
    gv    = clean_g(to_float(r.get("gross", "")), title)
    g     = round(gv / 1e6, 1) if gv else None
    bv    = clean_b(to_float(r.get("budget", "")), title) if is_us_film(r) else None
    b     = round(bv / 1e6, 1) if bv else None
    roi   = round((g - b) / b * 100, 1) if g is not None and b is not None and b > 0 else None
    genre = r.get("genres", "").split("|")[0].strip() or "Other"
    films_list.append({
        "t":       title,
        "y":       yr,
        "s":       sc,
        "g":       g,
        "b":       b,
        "r":       roi,
        "genre":   genre,
        "director": r.get("director_name", "").strip(),
        "rating":  r.get("content_rating", "").strip() or "Not Rated",
    })
films_list.sort(key=lambda f: -(f["s"] or 0))
films_list = films_list[:5000]

# ── Financial: scatter (budget vs gross) ──────────────────────────────────────

scatter_data = []
for r in rows:
    if not is_us_film(r): continue               # non-US budgets are in local currency
    b = to_float(r.get("budget", ""))
    g = to_float(r.get("gross", ""))
    if not b or not g: continue
    title = r.get("movie_title","").strip()
    if not is_valid_usd(b, g, title): continue   # additional USD sanity check
    genre = r.get("genres","").split("|")[0].strip() or "Other"
    if genre not in TOP8_GENRES: genre = "Other"
    yr = to_int(r.get("title_year","")) or 0
    roi = round(min((g - b) / b * 100, 1000), 1)   # cap at 1000% — micro-budget outliers excluded from scatter
    scatter_data.append({
        "x":  round(b/1e6, 1),
        "y":  round(g/1e6, 1),
        "r":  roi,
        "t":  title,
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

gp_map = defaultdict(lambda: {"gross":[], "budget":[], "score":[], "roi":[], "count":0})
for r in rows:
    genre = r.get("genres","").split("|")[0].strip()
    if not genre: continue
    gp_map[genre]["count"] += 1
    t2 = r.get("movie_title","").strip()
    g  = clean_g(to_float(r.get("gross","")), t2)   # US domestic gross — valid for all
    s2 = to_float(r.get("imdb_score",""))
    if g:  gp_map[genre]["gross"].append(g/1e6)
    if s2: gp_map[genre]["score"].append(s2)
    # Budget only from US productions — non-US budgets are in local currency
    if is_us_film(r):
        b2 = clean_b(to_float(r.get("budget","")), t2)
        if b2:
            gp_map[genre]["budget"].append(b2/1e6)
            if g and b2 > 0:
                roi_val = (g - b2) / b2 * 100
                # Cap per-film ROI at 1000% to keep genre averages meaningful.
                # Horror/Documentary micro-budget outliers (e.g. Paranormal Activity)
                # otherwise inflate the mean far above what is representatively useful.
                if roi_val <= 1000:
                    gp_map[genre]["roi"].append(roi_val)

genre_prof = []
for genre, d in gp_map.items():
    if d["count"] < 5: continue
    ag = round(sum(d["gross"])/len(d["gross"]),1) if d["gross"] else 0
    ab = round(sum(d["budget"])/len(d["budget"]),1) if d["budget"] else 0
    ar = round(sum(d["roi"])/len(d["roi"]), 1) if d["roi"] else 0
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

# ── Year-keyed keyword & country data (for dynamic year-range filter) ─────────

_tracked_kws = set(k for k,_ in kw_freq) | set(k for k,_,_ in kw_score)
_tracked_ctrs = set(c for c,_ in top_countries)

# {kw: {yr: [count, score_sum, score_cnt]}}
_kw_yr: dict = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0]))
for r in rows:
    yv = to_int(r.get("title_year","")) or 0
    if not yv: continue
    kws = r.get("plot_keywords","").strip()
    if not kws: continue
    sv = to_float(r.get("imdb_score",""))
    for kw in kws.split("|"):
        kw = kw.strip()
        if kw in _tracked_kws:
            _kw_yr[kw][yv][0] += 1
            if sv:
                _kw_yr[kw][yv][1] += sv
                _kw_yr[kw][yv][2] += 1
kw_year_data = {kw: {yr: vals for yr, vals in yd.items()} for kw, yd in _kw_yr.items()}

# {country: {yr: count}}
_ct_yr: dict = defaultdict(lambda: defaultdict(int))
for r in rows:
    yv = to_int(r.get("title_year","")) or 0
    if not yv: continue
    ct = r.get("country","").strip() or "Unknown"
    if ct in _tracked_ctrs:
        _ct_yr[ct][yv] += 1
country_year_data = {ct: {yr: cnt for yr, cnt in yd.items()} for ct, yd in _ct_yr.items()}

# Films with plot keywords per release year (for dynamic KPI)
kw_films_by_year = defaultdict(int)
for r in rows:
    yv = to_int(r.get("title_year", "")) or 0
    if yv and r.get("plot_keywords", "").strip():
        kw_films_by_year[yv] += 1

# ── Supporting film lists (tooltip drill-down backing data) ───────────────────

def _trunc(t):
    return t[:40] + "…" if len(t) > 40 else t

# -- Per-year: score, gross, ROI --
_yr_s, _yr_g, _yr_r = defaultdict(list), defaultdict(list), defaultdict(list)
for r in rows:
    yv = to_int(r.get("title_year","")) or 0
    if not yv: continue
    tv = _trunc(r.get("movie_title","").strip())
    sv = to_float(r.get("imdb_score",""))
    gv = clean_g(to_float(r.get("gross","")), "")
    if sv: _yr_s[yv].append({"t": tv, "v": round(sv, 1)})
    if gv: _yr_g[yv].append({"t": tv, "v": round(gv/1e6, 1)})
for d in scatter_data:
    if d["yr"]: _yr_r[d["yr"]].append({"t": _trunc(d["t"]), "v": d["r"]})
top_by_year = {
    yr: {
        "score": sorted(_yr_s[yr], key=lambda x: -x["v"])[:5],
        "gross": sorted(_yr_g[yr], key=lambda x: -x["v"])[:5],
        "roi":   sorted(_yr_r[yr], key=lambda x: -x["v"])[:5],
    }
    for yr in set(list(_yr_s) + list(_yr_g) + list(_yr_r))
}

# -- Per-genre: score, gross, ROI --
_gn_s, _gn_g, _gn_r = defaultdict(list), defaultdict(list), defaultdict(list)
for r in rows:
    gn = r.get("genres","").split("|")[0].strip()
    if not gn: continue
    tv = _trunc(r.get("movie_title","").strip())
    sv = to_float(r.get("imdb_score",""))
    gv = clean_g(to_float(r.get("gross","")), "")
    if sv: _gn_s[gn].append({"t": tv, "v": round(sv, 1)})
    if gv: _gn_g[gn].append({"t": tv, "v": round(gv/1e6, 1)})
for d in scatter_data:
    _gn_r[d["g"]].append({"t": _trunc(d["t"]), "v": d["r"]})
top_by_genre = {
    gn: {
        "score": sorted(_gn_s[gn], key=lambda x: -x["v"])[:5],
        "gross": sorted(_gn_g[gn], key=lambda x: -x["v"])[:5],
        "roi":   sorted(_gn_r[gn], key=lambda x: -x["v"])[:5],
    }
    for gn in set(list(_gn_s) + list(_gn_g) + list(_gn_r))
}

# -- Per-genre × year: top 3 by score (for genre trends line) --
_gyt = defaultdict(lambda: defaultdict(list))
for r in rows:
    yv = to_int(r.get("title_year","")) or 0
    gn = r.get("genres","").split("|")[0].strip()
    if not yv or not gn: continue
    sv = to_float(r.get("imdb_score",""))
    if sv: _gyt[gn][yv].append({"t": _trunc(r.get("movie_title","").strip()), "v": round(sv,1)})
top_by_genre_year = {
    gn: {yr: sorted(fs, key=lambda x: -x["v"])[:3] for yr, fs in ym.items()}
    for gn, ym in _gyt.items()
}

# -- Per-score-bin: top 5 by score --
_sbn = defaultdict(list)
for r in rows:
    sv = to_float(r.get("imdb_score",""))
    if not sv: continue
    bk = str(round(1.0 + int((sv-1.0)/0.5)*0.5, 1))
    _sbn[bk].append({"t": _trunc(r.get("movie_title","").strip()), "v": round(sv,1)})
top_by_score_bin = {k: sorted(v, key=lambda x: -x["v"])[:5] for k, v in _sbn.items()}

# -- Per-content-rating: top 5 by score --
_rat = defaultdict(list)
for r in rows:
    cr = r.get("content_rating","").strip() or "Not Rated"
    sv = to_float(r.get("imdb_score",""))
    if sv: _rat[cr].append({"t": _trunc(r.get("movie_title","").strip()), "v": round(sv,1)})
top_by_rating = {k: sorted(v, key=lambda x: -x["v"])[:5] for k, v in _rat.items()}

# -- Per-country: top 5 by score --
_ctr = defaultdict(list)
for r in rows:
    ct = r.get("country","").strip() or "Unknown"
    sv = to_float(r.get("imdb_score",""))
    if sv: _ctr[ct].append({"t": _trunc(r.get("movie_title","").strip()), "v": round(sv,1)})
top_by_country = {k: sorted(v, key=lambda x: -x["v"])[:5] for k, v in _ctr.items()}

# -- Per-keyword: top 5 by score (displayed keywords only) --
_dkw = set(k for k,_ in kw_freq) | set(k for k,_,_ in kw_score)
_kfw = defaultdict(list)
for r in rows:
    kws = r.get("plot_keywords","").strip()
    if not kws: continue
    sv = to_float(r.get("imdb_score",""))
    tv = _trunc(r.get("movie_title","").strip())
    for kw in kws.split("|"):
        kw = kw.strip()
        if kw in _dkw:
            _kfw[kw].append({"t": tv, "v": round(sv,1) if sv else 0})
top_by_kw = {k: sorted(v, key=lambda x: -x["v"])[:5] for k, v in _kfw.items()}

# ── Genre-year data (compact, for JS dynamic filter) ─────────────────────────

gyd = []
for r in rows:
    yr_val = to_int(r.get("title_year","")) or 0
    if not yr_val: continue
    genre_val = r.get("genres","").split("|")[0].strip()
    if not genre_val: continue
    t3     = r.get("movie_title","").strip()
    sc_val = to_float(r.get("imdb_score",""))
    gv_val = clean_g(to_float(r.get("gross","")), t3)            # None if bad currency
    # Budget only valid for US films — non-US use local currency
    bv_val = clean_b(to_float(r.get("budget","")), t3) if is_us_film(r) else None
    cr_val = r.get("content_rating","").strip() or "Not Rated"
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
    "actors": actor_stats,
    "films": films_list,
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
    "kw_year_data": kw_year_data,
    "kw_films_by_year": dict(kw_films_by_year),
    "country_year_data": country_year_data,
    "top_by_year":        top_by_year,
    "top_by_genre":       top_by_genre,
    "top_by_genre_year":  top_by_genre_year,
    "top_by_score_bin":   top_by_score_bin,
    "top_by_rating":      top_by_rating,
    "top_by_country":     top_by_country,
    "top_by_kw":          top_by_kw,
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
@keyframes kpiPulse {{
  0%   {{ color: var(--accent2); }}
  100% {{ color: inherit; }}
}}
.kpi-value.kpi-updated {{ animation: kpiPulse .6s ease; }}
.kpi.accent .kpi-value.kpi-updated {{ animation-name: kpiPulse; }}
.kpi.pos .kpi-value.kpi-updated {{ animation-name: kpiPulse; }}
.kpi.warn .kpi-value.kpi-updated {{ animation-name: kpiPulse; }}

/* ── Charts grid ── */
.charts-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}
.chart-card {{
  position: relative;
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

/* ── Data disclaimer note ── */
.data-note {{
  background: rgba(237,201,72,.07);
  border: 1px solid rgba(237,201,72,.25);
  border-radius: 6px;
  color: #b8a050;
  font-size: 11.5px;
  line-height: 1.5;
  padding: 8px 14px;
  margin-bottom: 14px;
}}

/* ── Chart info popup ── */
.chart-title-row {{
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 3px;
}}
.chart-info-btn {{
  background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 15px; line-height: 1;
  padding: 0 2px; opacity: 0.55; transition: opacity .15s, color .15s;
  flex-shrink: 0; margin-top: 1px;
}}
.chart-info-btn:hover, .chart-info-btn.active {{ opacity: 1; color: var(--accent); }}
.chart-zoom-btn {{
  background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 14px; line-height: 1;
  padding: 0 2px; opacity: 0.55; transition: opacity .15s, color .15s;
  flex-shrink: 0; margin-top: 1px; margin-left: 4px;
}}
.chart-zoom-btn:hover {{ opacity: 1; color: var(--accent); }}
.chart-title-actions {{ display: flex; align-items: flex-start; gap: 2px; flex-shrink: 0; }}

/* ── Unified chart tooltip ── */
#chart-tooltip {{
  position: fixed; z-index: 10001; display: none;
  background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px;
  padding: 12px 16px; min-width: 200px; max-width: 280px;
  pointer-events: none; box-shadow: 0 6px 24px rgba(0,0,0,.6);
  font-family: system-ui, sans-serif;
  opacity: 0; transition: opacity 150ms;
}}

/* ── Chart zoom modal ── */
#zoom-modal {{
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0,0,0,.75);
  display: none; align-items: center; justify-content: center;
  padding: 20px;
}}
#zoom-modal.visible {{ display: flex; }}
.zoom-modal-card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; max-width: 90vw; max-height: 90vh;
  width: 100%; display: flex; flex-direction: column;
  transform: scale(0.95); opacity: 0;
  transition: transform .2s ease, opacity .2s ease;
  box-shadow: 0 8px 40px rgba(0,0,0,.6);
}}
#zoom-modal.visible .zoom-modal-card {{ transform: scale(1); opacity: 1; }}
.zoom-modal-header {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
}}
.zoom-modal-title {{ font-size: 14px; font-weight: 600; }}
.zoom-modal-close {{
  background: none; border: none; color: var(--muted);
  font-size: 18px; cursor: pointer; line-height: 1; padding: 2px 6px;
}}
.zoom-modal-close:hover {{ color: var(--text); }}
.zoom-modal-body {{
  flex: 1; min-height: 0; padding: 16px 18px 18px;
  position: relative; height: 70vh;
}}
#zoom-canvas {{ width: 100% !important; height: 100% !important; }}
.chart-info-popup {{
  position: absolute; top: 36px; right: 12px; z-index: 200;
  min-width: 220px; max-width: 320px;
  background: rgba(15,17,23,.97); border: 1px solid var(--border);
  border-radius: 7px; padding: 12px 14px;
  font-size: 12px; line-height: 1.55;
  box-shadow: 0 4px 20px rgba(0,0,0,.5);
  opacity: 0; pointer-events: none;
  transition: opacity .15s;
}}
.chart-info-popup.visible {{ opacity: 1; pointer-events: auto; }}
.chart-info-popup::before {{
  content: ''; position: absolute; top: -7px; right: 16px;
  border-left: 7px solid transparent; border-right: 7px solid transparent;
  border-bottom: 7px solid var(--border);
}}
.chart-info-popup::after {{
  content: ''; position: absolute; top: -5px; right: 17px;
  border-left: 6px solid transparent; border-right: 6px solid transparent;
  border-bottom: 6px solid rgba(15,17,23,.97);
}}
.info-section + .info-section {{ margin-top: 10px; }}
.info-label {{
  font-size: 9px; text-transform: uppercase; letter-spacing: .7px;
  color: var(--accent); margin-bottom: 4px; font-weight: 600;
}}
.info-text {{ color: #b8c0cc; }}

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

/* ── Sub-tabs (Director & Cast page) ── */
.sub-tab-bar {{
  display: flex; gap: 4px; margin-bottom: 18px;
  border-bottom: 1px solid var(--border); padding-bottom: 0;
}}
.sub-tab {{
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--muted); font-size: 12px; font-weight: 500;
  padding: 6px 14px; cursor: pointer; margin-bottom: -1px;
  transition: color .15s, border-color .15s;
}}
.sub-tab:hover {{ color: var(--text); }}
.sub-tab.active {{ color: var(--text); border-bottom-color: #59a14f; font-weight: 600; }}
.sub-tab-panel {{ display: none; }}
.sub-tab-panel.active {{ display: block; }}

/* ── Film leaderboard filters ── */
.film-filters {{
  display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; align-items: center;
}}
.film-filter-select {{
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); font-size: 12px; padding: 6px 10px; outline: none; cursor: pointer;
}}
.film-filter-select:focus {{ border-color: var(--accent); }}
.film-sort-group {{ display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }}
.film-sort-label {{ font-size: 11px; color: var(--muted); margin-right: 2px; }}
.film-sort-btn {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; color: var(--muted); font-size: 11px; padding: 5px 10px; cursor: pointer;
}}
.film-sort-btn.active {{ border-color: #59a14f; color: #59a14f; }}
.sort-dir-btn {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; color: var(--muted); font-size: 11px; padding: 5px 8px; cursor: pointer;
  min-width: 28px;
}}
.sort-dir-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
.role-pill {{
  display: inline-block; font-size: 11px; border-radius: 4px; padding: 1px 6px;
}}
.role-pill.lead {{ background: rgba(78,121,167,.15); color: #4e79a7; }}
.role-pill.support {{ background: rgba(242,142,43,.12); color: #f28e2b; }}
.role-pill.featured {{ background: rgba(136,146,164,.12); color: var(--muted); }}
.col-top {{ color: #59a14f; font-weight: 600; }}
.film-table td {{ font-size: 12px; }}
.film-table .film-title {{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

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
    <div class="kpi"><div class="kpi-label">Total Films</div><div class="kpi-value" id="kpi-total-films">{total_films:,}</div><div class="kpi-sub" id="kpi-total-films-sub">in selected range</div></div>
    <div class="kpi accent"><div class="kpi-label">Avg IMDB Score</div><div class="kpi-value" id="kpi-avg-score">{global_avg_score}</div><div class="kpi-sub" id="kpi-avg-score-sub">in selected range</div></div>
    <div class="kpi"><div class="kpi-label">Total Gross</div><div class="kpi-value" id="kpi-total-gross" style="font-size:18px">${int(sum(g for g in total_gross_yr if g)):,}M</div><div class="kpi-sub" id="kpi-total-gross-sub">USD in selected range</div></div>
    <div class="kpi"><div class="kpi-label">Avg Budget</div><div class="kpi-value" id="kpi-avg-budget" style="font-size:18px">${round(sum(b for b in avg_budget_yr if b)/len([b for b in avg_budget_yr if b]),1) if [b for b in avg_budget_yr if b] else 0}M</div><div class="kpi-sub" id="kpi-avg-budget-sub">US productions only</div></div>
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
    <div class="kpi"><div class="kpi-label">Films Analyzed</div><div class="kpi-value" id="kpi-scatter-pts">{len(scatter_data):,}</div><div class="kpi-sub" id="kpi-scatter-pts-sub">US productions with budget &amp; gross</div></div>
    <div class="kpi warn"><div class="kpi-label">Avg ROI</div><div class="kpi-value" id="kpi-avg-roi">{avg_roi_global:+.0f}%</div><div class="kpi-sub">gross vs budget</div></div>
    <div class="kpi pos"><div class="kpi-label">Profitable</div><div class="kpi-value" id="kpi-profitable-pct">{round(profitable_count/len(scatter_data)*100) if scatter_data else 0}%</div><div class="kpi-sub" id="kpi-profitable-pct-sub">of analyzed films</div></div>
    <div class="kpi"><div class="kpi-label">Best ROI Genre</div><div class="kpi-value" id="kpi-top-roi-genre" style="font-size:16px">{best_roi_genre['genre']}</div><div class="kpi-sub" id="kpi-top-roi-genre-sub">{best_roi_genre['avg_roi']:+.0f}% avg ROI</div></div>
  </div>
  <div class="data-note">⚠ Budget figures restricted to US productions only. Non-US films record budgets in local currency (JPY, EUR, INR…) while gross is US domestic (USD), making direct ROI comparison invalid. Gross revenue charts include all countries.</div>
  <div class="charts-grid">
    <div class="chart-card wide"><div class="chart-title">Budget vs Gross — Scatter</div><div class="chart-caption">US productions only · log scale · ±2.5% jitter · darker = denser cluster · hover for details</div><div class="chart-wrap scatter-h"><canvas id="cScatter"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Average ROI per Year</div><div class="chart-caption">Mean per-film ROI averaged by year · US productions only</div><div class="chart-wrap"><canvas id="cROI"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Top Genres by Avg Gross</div><div class="chart-caption">Mean reported gross revenue per film (USD millions)</div><div class="chart-wrap hbar-sm"><canvas id="cGenreGross"></canvas></div></div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: GENRE ────────────────────────────────── -->
<div class="page" id="page-genre">
  <div class="kpi-row">
    <div class="kpi accent"><div class="kpi-label">Top Gross Genre</div><div class="kpi-value" id="kpi-top-gross-genre" style="font-size:16px">{top_gross_genre['genre']}</div><div class="kpi-sub" id="kpi-top-gross-genre-sub">${top_gross_genre['avg_gross']:.0f}M avg gross</div></div>
    <div class="kpi pos"><div class="kpi-label">Best ROI Genre</div><div class="kpi-value" id="kpi-best-roi-genre" style="font-size:16px">{best_roi_genre['genre']}</div><div class="kpi-sub" id="kpi-best-roi-genre-sub">{best_roi_genre['avg_roi']:+.0f}% avg ROI</div></div>
    <div class="kpi"><div class="kpi-label">Top Rated Genre</div><div class="kpi-value" id="kpi-top-rated-genre" style="font-size:16px">{top_rated_genre['genre']}</div><div class="kpi-sub" id="kpi-top-rated-genre-sub">{top_rated_genre['avg_score']} avg score</div></div>
    <div class="kpi"><div class="kpi-label">Most Common Genre</div><div class="kpi-value" id="kpi-most-common-genre" style="font-size:16px">{most_common_genre['genre']}</div><div class="kpi-sub" id="kpi-most-common-genre-sub">{most_common_genre['count']:,} films</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card"><div class="chart-title">Genre Profitability (Avg ROI)</div><div class="chart-caption">Avg of per-film ROI by genre · US productions only · all years</div><div class="chart-wrap hbar"><canvas id="cGenreROI"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Genre Avg IMDB Score</div><div class="chart-caption">Mean user rating per genre · all years</div><div class="chart-wrap hbar"><canvas id="cGenreScore"></canvas></div></div>
    <div class="chart-card wide"><div class="chart-title">Genre Trends Over Time</div><div class="chart-caption">Film count by primary genre per year · responds to year filter</div><div class="chart-wrap tall"><canvas id="cGenreTrends"></canvas></div></div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: DIRECTORS ────────────────────────────── -->
<div class="page" id="page-directors">
  <div class="section-header">
    <h2>Director &amp; Cast Analytics</h2>
    <p>Leaderboards for directors, actors, and individual films · stats reflect active year range</p>
  </div>

  <nav class="sub-tab-bar">
    <button class="sub-tab active" data-subtab="directors">Directors</button>
    <button class="sub-tab" data-subtab="cast">Cast (Actors)</button>
    <button class="sub-tab" data-subtab="films">Films</button>
  </nav>

  <!-- Directors tab -->
  <div id="sub-directors" class="sub-tab-panel active">
    <div class="dir-controls">
      <input class="dir-search" id="dirSearch" type="text" placeholder="Search directors..." autocomplete="off"/>
      <div class="sort-btns" id="dirSortBtns">
        <button class="sort-btn active" data-sort="gross">Total Gross</button>
        <button class="sort-btn" data-sort="score">Avg Score</button>
        <button class="sort-btn" data-sort="count">Film Count</button>
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

  <!-- Cast (Actors) tab -->
  <div id="sub-cast" class="sub-tab-panel">
    <div class="dir-controls">
      <input class="dir-search" id="actorSearch" type="text" placeholder="Search actors..." autocomplete="off"/>
      <div class="sort-btns" id="actorSortBtns">
        <button class="sort-btn active" data-sort="gross">Total Gross</button>
        <button class="sort-btn" data-sort="score">Avg Score</button>
        <button class="sort-btn" data-sort="count">Film Count</button>
      </div>
    </div>
    <div class="dir-table-wrap">
      <div class="dir-loading" id="actorLoading"><div class="spinner"></div><span>Loading...</span></div>
      <table class="dir-table">
        <thead><tr>
          <th style="width:40px">#</th>
          <th>Actor</th>
          <th class="num">Films</th>
          <th class="num">Avg Score</th>
          <th class="num">Total Gross</th>
          <th>Best Film (by score)</th>
        </tr></thead>
        <tbody id="actorTbody"></tbody>
      </table>
    </div>
    <div class="dir-pagination">
      <span class="pagination-info" id="actorPageInfo"></span>
      <div class="pagination-btns">
        <button class="page-btn" id="actorPagePrev">&#8592; Prev</button>
        <span class="page-indicator" id="actorPageIndicator"></span>
        <button class="page-btn" id="actorPageNext">Next &#8594;</button>
      </div>
    </div>
  </div>

  <!-- Films tab -->
  <div id="sub-films" class="sub-tab-panel">
    <div class="dir-controls">
      <input class="dir-search" id="filmSearch" type="text" placeholder="Search title or director..." autocomplete="off"/>
    </div>
    <div class="film-filters">
      <select class="film-filter-select" id="filmGenreFilter">
        <option value="">All Genres</option>
      </select>
      <select class="film-filter-select" id="filmRatingFilter">
        <option value="">All Ratings</option>
        <option value="PG">PG</option>
        <option value="PG-13">PG-13</option>
        <option value="R">R</option>
        <option value="G">G</option>
        <option value="Not Rated">Not Rated</option>
      </select>
      <div class="film-sort-group">
        <span class="film-sort-label">Sort by:</span>
        <button class="film-sort-btn active" data-fsort="score">IMDB Score</button>
        <button class="film-sort-btn" data-fsort="gross">Gross</button>
        <button class="film-sort-btn" data-fsort="budget">Budget</button>
        <button class="film-sort-btn" data-fsort="roi">ROI</button>
        <button class="film-sort-btn" data-fsort="year">Year</button>
        <button class="film-sort-btn" data-fsort="title">Title</button>
        <button class="sort-dir-btn" id="filmSortDir" title="Toggle sort direction">&#8595;</button>
      </div>
    </div>
    <div class="dir-table-wrap">
      <div class="dir-loading" id="filmLoading"><div class="spinner"></div><span>Loading...</span></div>
      <table class="dir-table film-table">
        <thead><tr>
          <th>Title</th>
          <th class="num">Year</th>
          <th>Genre</th>
          <th>Director</th>
          <th>Rating</th>
          <th class="num">Score</th>
          <th class="num">Gross</th>
          <th class="num">Budget</th>
          <th class="num">ROI</th>
        </tr></thead>
        <tbody id="filmTbody"></tbody>
      </table>
    </div>
    <div class="dir-pagination">
      <span class="pagination-info" id="filmPageInfo"></span>
      <div class="pagination-btns">
        <button class="page-btn" id="filmPagePrev">&#8592; Prev</button>
        <span class="page-indicator" id="filmPageIndicator"></span>
        <button class="page-btn" id="filmPageNext">Next &#8594;</button>
      </div>
    </div>
  </div>
</div>

<!-- ─────────────────────────── PAGE: ENGAGEMENT ──────────────────────────── -->
<div class="page" id="page-engagement">
  <div class="kpi-row">
    <div class="kpi accent"><div class="kpi-label">Avg Votes / Film</div><div class="kpi-value" id="kpi-avg-votes">{avg_votes:,}</div><div class="kpi-sub">num_voted_users</div></div>
    <div class="kpi pos"><div class="kpi-label">High Score Films</div><div class="kpi-value" id="kpi-high-score-pct">{round(sum(1 for r in rows if to_float(r.get('imdb_score','')) and to_float(r.get('imdb_score',''))>=7.5)/len(all_scores)*100) if all_scores else 0}%</div><div class="kpi-sub" id="kpi-high-score-pct-sub">score ≥ 7.5</div></div>
    <div class="kpi"><div class="kpi-label">Top Rated Film</div><div class="kpi-value" id="kpi-top-rated-kpi" style="font-size:13px;line-height:1.3">{films_list[0]['t'][:28]}{'…' if len(films_list[0]['t'])>28 else ''}</div><div class="kpi-sub" id="kpi-top-rated-kpi-sub">★{films_list[0]['s'] or '—'}</div></div>
    <div class="kpi"><div class="kpi-label">Most Voted Film</div><div class="kpi-value" id="kpi-top-votes-kpi" style="font-size:13px;line-height:1.3">{top_voted_title[:28]}{'…' if len(top_voted_title)>28 else ''}</div><div class="kpi-sub" id="kpi-top-votes-kpi-sub">{top_voted_n:,} votes</div></div>
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
    <div class="kpi"><div class="kpi-label">Unique Keywords</div><div class="kpi-value" id="kpi-unique-kw">{total_kw:,}</div><div class="kpi-sub" id="kpi-unique-kw-sub">in selected range</div></div>
    <div class="kpi"><div class="kpi-label">Films with Keywords</div><div class="kpi-value" id="kpi-films-with-kw">{films_with_kw:,}</div><div class="kpi-sub" id="kpi-films-with-kw-sub">in selected range</div></div>
    <div class="kpi accent"><div class="kpi-label">Most Used Keyword</div><div class="kpi-value" id="kpi-top-kw" style="font-size:15px">{kw_freq[0][0] if kw_freq else 'N/A'}</div><div class="kpi-sub" id="kpi-top-kw-sub">{kw_freq[0][1] if kw_freq else 0:,} films</div></div>
    <div class="kpi"><div class="kpi-label">Highest Scoring Kw.</div><div class="kpi-value" id="kpi-top-kw-score" style="font-size:15px">{top_kw_by_score}</div><div class="kpi-sub" id="kpi-top-kw-score-sub">by avg IMDB score</div></div>
  </div>
  <div class="charts-grid">
    <div class="chart-card"><div class="chart-title">Top 20 Keywords by Frequency</div><div class="chart-caption">Most common plot keywords across dataset</div><div class="chart-wrap hbar"><canvas id="cKwFreq"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Top 20 Keywords by Avg Score</div><div class="chart-caption">Keywords associated with highest-rated films (min 10 films)</div><div class="chart-wrap hbar"><canvas id="cKwScore"></canvas></div></div>
    <div class="chart-card wide"><div class="chart-title">Country Distribution</div><div class="chart-caption">Number of films per country of production</div><div class="chart-wrap hbar-sm"><canvas id="cCountries"></canvas></div></div>
  </div>
</div>

<div id="chart-tooltip"></div>

<div id="zoom-modal">
  <div class="zoom-modal-card">
    <div class="zoom-modal-header">
      <span class="zoom-modal-title" id="zoom-modal-title"></span>
      <button class="zoom-modal-close" id="zoom-modal-close" title="Close">&#10005;</button>
    </div>
    <div class="zoom-modal-body">
      <canvas id="zoom-canvas"></canvas>
    </div>
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
      footerColor:"#6b7a90", footerFont:{{ size:10, style:"italic" }},
      footerMarginTop: 6,
    }}
  }},
  scales: {{
    x: {{ ticks:{{ color:"#8892a4", font:{{ size:10 }}, maxRotation:45 }}, grid:{{ color:"#2a2d3a" }} }},
    y: {{ ticks:{{ color:"#8892a4", font:{{ size:10 }} }}, grid:{{ color:"#2a2d3a" }} }}
  }}
}};

let _mergeDepth = 0;
function merge(a, b) {{
  _mergeDepth++;
  if (_mergeDepth > 20) {{ _mergeDepth--; return a; }}
  const r = JSON.parse(JSON.stringify(a));
  for (const k in b) {{
    if (b[k] && typeof b[k]==="object" && !Array.isArray(b[k])) r[k] = merge(r[k]||{{}}, b[k]);
    else r[k] = b[k];
  }}
  _mergeDepth--;
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
  directors: () => {{ initDirectorsPage(); }},
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
  updateKPIs(lo, hi);
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
      const pts = initFinancial._scatterPts(g, lo, hi);
      C.scatter.data.datasets[i].data = pts;
      C.scatter.data.datasets[i].label = `${{g}} (${{pts.length}})`;
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
    // Genre ROI — rank-based alpha keeps all bars visible regardless of value spread
    const gpR = [...gp].sort((a,b)=>b.avg_roi-a.avg_roi).slice(0,15);
    C.genreROI.data.labels = gpR.map(d=>d.genre);
    C.genreROI.data.datasets[0].data = gpR.map(d=>d.avg_roi);
    C.genreROI.data.datasets[0].backgroundColor = gpR.map((d,i) => {{
      const a = (0.9 - 0.4*(i/Math.max(gpR.length-1,1))).toFixed(2);
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
  if (INIT.keywords) {{
    const kd = getKwData(lo, hi);
    const kwN = Math.max(kd.freq.length, 1);
    C.kwFreq.data.labels = kd.freq.map(d=>d[0]);
    C.kwFreq.data.datasets[0].data = kd.freq.map(d=>d[1]);
    C.kwFreq.data.datasets[0].backgroundColor = kd.freq.map((_,i)=>`rgba(78,121,167,${{(0.9-0.5*i/kwN).toFixed(2)}})` );
    C.kwFreq.update();
    C.kwScore.data.labels = kd.score.map(d=>d[0]);
    C.kwScore.data.datasets[0].data = kd.score.map(d=>d[1]);
    C.kwScore.data.datasets[0].backgroundColor = kd.score.map(d=>scoreColor(d[1], 0.85));
    C.kwScore.update();
    const cd = getCountryData(lo, hi);
    const ctN = Math.max(cd.length, 1);
    C.countries.data.labels = cd.map(d=>d[0]);
    C.countries.data.datasets[0].data = cd.map(d=>d[1]);
    C.countries.data.datasets[0].backgroundColor = cd.map((_,i)=>`rgba(89,161,79,${{(0.9-0.5*i/ctN).toFixed(2)}})` );
    C.countries.update();
  }}
  filteredList = buildFilteredList(); currentPage=0; renderTable();
  actorFilteredList = buildActorFilteredList(); actorCurrentPage=0; renderActorTable();
  filmFilteredList = buildFilmFilteredList(); filmCurrentPage=0; renderFilmTable();
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

// ── KPI dynamic updates ─────────────────────────────────────────────────────

function setKpi(id, text) {{
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.remove('kpi-updated');
  void el.offsetWidth;
  el.classList.add('kpi-updated');
  setTimeout(() => el.classList.remove('kpi-updated'), 600);
}}

function setKpiSub(id, text) {{
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}}

function fmtGrossKpi(v) {{
  if (v == null || v === 0) return '$0';
  if (v >= 1000) return `$${{(v/1000).toFixed(1)}}B`;
  return `$${{Math.round(v)}}M`;
}}

function updateKPIs(lo, hi) {{
  const s = getYearSlice(lo, hi);
  const gp = getGenreProf(lo, hi);

  const totalFilms = s.movies.reduce((a, b) => a + b, 0);
  const scores = s.score.filter(x => x != null);
  const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length * 100) / 100 : '—';
  const totalGross = s.gross.filter(x => x != null).reduce((a, b) => a + b, 0);
  const budgets = s.budget.filter(x => x != null);
  const avgBudget = budgets.length ? Math.round(budgets.reduce((a, b) => a + b, 0) / budgets.length * 10) / 10 : null;

  setKpi('kpi-total-films', totalFilms.toLocaleString());
  setKpiSub('kpi-total-films-sub', `${{lo}}–${{hi}}`);
  setKpi('kpi-avg-score', String(avgScore));
  setKpi('kpi-total-gross', fmtGrossKpi(totalGross));
  setKpi('kpi-avg-budget', avgBudget != null ? fmtGrossKpi(avgBudget) : '—');

  const scatterInRange = D.scatter.filter(d => d.yr >= lo && d.yr <= hi);
  const roiVals = scatterInRange.map(d => d.r);
  const avgRoi = roiVals.length ? Math.round(roiVals.reduce((a, b) => a + b, 0) / roiVals.length) : 0;
  const profitablePct = roiVals.length ? Math.round(roiVals.filter(r => r > 0).length / roiVals.length * 100) : 0;
  const bestRoiG = gp.length ? [...gp].sort((a, b) => b.avg_roi - a.avg_roi)[0] : null;

  setKpi('kpi-scatter-pts', scatterInRange.length.toLocaleString());
  setKpi('kpi-avg-roi', `${{avgRoi >= 0 ? '+' : ''}}${{avgRoi}}%`);
  setKpi('kpi-profitable-pct', `${{profitablePct}}%`);
  setKpi('kpi-top-roi-genre', bestRoiG ? bestRoiG.genre : 'N/A');
  setKpiSub('kpi-top-roi-genre-sub', bestRoiG ? `${{bestRoiG.avg_roi >= 0 ? '+' : ''}}${{Math.round(bestRoiG.avg_roi)}}% avg ROI` : '');

  const topGrossG = gp.length ? [...gp].sort((a, b) => b.avg_gross - a.avg_gross)[0] : null;
  const topRatedG = gp.length ? [...gp].sort((a, b) => b.avg_score - a.avg_score)[0] : null;
  const mostCommonG = gp.length ? [...gp].sort((a, b) => b.count - a.count)[0] : null;
  const bestRoiG2 = bestRoiG;

  setKpi('kpi-top-gross-genre', topGrossG ? topGrossG.genre : 'N/A');
  setKpiSub('kpi-top-gross-genre-sub', topGrossG ? `${{fmtGrossKpi(topGrossG.avg_gross)}} avg gross` : '');
  setKpi('kpi-best-roi-genre', bestRoiG2 ? bestRoiG2.genre : 'N/A');
  setKpiSub('kpi-best-roi-genre-sub', bestRoiG2 ? `${{bestRoiG2.avg_roi >= 0 ? '+' : ''}}${{Math.round(bestRoiG2.avg_roi)}}% avg ROI` : '');
  setKpi('kpi-top-rated-genre', topRatedG ? topRatedG.genre : 'N/A');
  setKpiSub('kpi-top-rated-genre-sub', topRatedG ? `${{topRatedG.avg_score}} avg score` : '');
  setKpi('kpi-most-common-genre', mostCommonG ? mostCommonG.genre : 'N/A');
  setKpiSub('kpi-most-common-genre-sub', mostCommonG ? `${{mostCommonG.count.toLocaleString()}} films` : '');

  const eng = D.engagement.filter(d => d.yr >= lo && d.yr <= hi);
  const avgVotes = eng.length ? Math.round(eng.reduce((a, d) => a + d.y * 1000, 0) / eng.length) : 0;
  const highScorePct = eng.length ? Math.round(eng.filter(d => d.x >= 7.5).length / eng.length * 100) : 0;
  const topRated = eng.length ? eng.reduce((a, b) => (b.x > a.x ? b : a)) : null;
  const topVotes = eng.length ? eng.reduce((a, b) => (b.y > a.y ? b : a)) : null;

  setKpi('kpi-avg-votes', avgVotes.toLocaleString());
  setKpi('kpi-high-score-pct', `${{highScorePct}}%`);
  if (topRated) {{
    const trTitle = topRated.t.length > 28 ? topRated.t.slice(0, 28) + '…' : topRated.t;
    setKpi('kpi-top-rated-kpi', trTitle);
    setKpiSub('kpi-top-rated-kpi-sub', `★${{topRated.x}}`);
  }}
  if (topVotes) {{
    const tvTitle = topVotes.t.length > 28 ? topVotes.t.slice(0, 28) + '…' : topVotes.t;
    setKpi('kpi-top-votes-kpi', tvTitle);
    setKpiSub('kpi-top-votes-kpi-sub', `${{Math.round(topVotes.y * 1000).toLocaleString()}} votes`);
  }}

  let uniqueKw = 0;
  for (const yrs of Object.values(D.kw_year_data)) {{
    let c = 0;
    for (let yr = lo; yr <= hi; yr++) if (yrs[yr]) c += yrs[yr][0];
    if (c > 0) uniqueKw++;
  }}
  let filmsWithKw = 0;
  for (let yr = lo; yr <= hi; yr++) filmsWithKw += (D.kw_films_by_year[yr] || 0);
  const kd = getKwData(lo, hi);

  setKpi('kpi-unique-kw', uniqueKw.toLocaleString());
  setKpi('kpi-films-with-kw', filmsWithKw.toLocaleString());
  setKpiSub('kpi-films-with-kw-sub', `of ${{totalFilms.toLocaleString()}} in range`);
  setKpi('kpi-top-kw', kd.freq.length ? kd.freq[0][0] : 'N/A');
  setKpiSub('kpi-top-kw-sub', kd.freq.length ? `${{kd.freq[0][1].toLocaleString()}} films` : '');
  setKpi('kpi-top-kw-score', kd.score.length ? kd.score[0][0] : 'N/A');
  setKpiSub('kpi-top-kw-score-sub', kd.score.length ? `★${{kd.score[0][1]}} avg score` : '');
}}

// ── Unified chart tooltip ────────────────────────────────────────────────────

const chartTooltip = document.getElementById('chart-tooltip');

function tooltipAccent(fmtStr) {{
  if (fmtStr.includes('$')) return '#59a14f';
  if (fmtStr.includes('%')) return '#edc948';
  return '#f28e2b';
}}

function truncTipTitle(t, n=32) {{
  return t.length > n ? t.slice(0, n) + '…' : t;
}}

function buildTooltipHTML(title, value, films, fmt) {{
  let html = `<div style="color:#f28e2b;font-weight:700;font-size:12px;margin-bottom:4px">${{title}}</div>`;
  if (value) html += `<div style="color:#fff;font-weight:700;font-size:14px">${{value}}</div>`;
  if (films && films.length && fmt) {{
    html += `<div style="border-top:1px solid #2a2d3a;margin:8px 0"></div>`;
    html += `<div style="color:#8892a4;font-size:10px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Top films</div>`;
    films.slice(0, 4).forEach(f => {{
      const badge = fmt(f.v);
      const accent = tooltipAccent(badge);
      html += `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px">`;
      html += `<span style="color:#fff;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0">${{truncTipTitle(f.t)}}</span>`;
      html += `<span style="background:#2a2d3a;border-radius:4px;padding:1px 6px;font-size:10px;font-weight:600;color:${{accent}};flex-shrink:0">${{badge}}</span>`;
      html += `</div>`;
    }});
  }}
  return html;
}}


function hideChartTooltip() {{
  if (!chartTooltip) return;
  chartTooltip.style.opacity = '0';
  chartTooltip.style.display = 'none';
}}

function positionChartTooltip(context) {{
  const canvas = context.chart.canvas;
  const {{ caretX, caretY }} = context.tooltip;
  const rect = canvas.getBoundingClientRect();
  const pad = 12;
  let x = rect.left + caretX + 12;
  let y = rect.top + caretY + 12;
  const pw = chartTooltip.offsetWidth || 220;
  const ph = chartTooltip.offsetHeight || 100;
  if (x + pw + pad > window.innerWidth) x = Math.max(pad, rect.left + caretX - pw - 12);
  if (y + ph + pad > window.innerHeight) y = Math.max(pad, rect.top + caretY - ph - 12);
  chartTooltip.style.left = x + 'px';
  chartTooltip.style.top = y + 'px';
}}

function showCustomTooltip(context, lookupFn) {{
  if (context.tooltip.opacity === 0) {{ hideChartTooltip(); return; }}
  const dp = context.tooltip.dataPoints?.[0];
  if (!dp) {{ hideChartTooltip(); return; }}
  let info;
  try {{
    info = lookupFn(dp, context.chart);
  }} catch(e) {{
    hideChartTooltip(); return;
  }}
  if (!info) {{ hideChartTooltip(); return; }}
  chartTooltip.innerHTML = buildTooltipHTML(info.title, info.value, info.films, info.fmt);
  chartTooltip.style.display = 'block';
  chartTooltip.style.opacity = '1';
  positionChartTooltip(context);
}}

// Registers an external tooltip handler on a chart.
// Options are assigned directly (Chart.js reads them lazily on next hover — no update() needed).
function bindExternalTooltip(chart, lookupFn) {{
  try {{
    // chart.options is a Chart.js Proxy whose set-trap causes internal
    // notification loops → stack overflow. Write to the raw plain-object
    // config instead, then call update() once from normal call flow.
    const rawOpts = chart.config._config.options || {{}};
    rawOpts.plugins = rawOpts.plugins || {{}};
    rawOpts.plugins.tooltip = {{
      enabled: false,
      external: ctx => showCustomTooltip(ctx, lookupFn),
    }};
    chart.config._config.options = rawOpts;
    chart.canvas.addEventListener('mouseleave', hideChartTooltip);
    chart.update();
  }} catch(e) {{
  }}
}}

// ── Dynamic aggregation helpers (use D.gyd for year-aware genre/score stats) ──

function getGenreProf(lo, hi) {{
  const gmap = {{}};
  D.gyd.filter(d => d[1]>=lo && d[1]<=hi).forEach(([genre, , sc, gross, budget]) => {{
    if (!gmap[genre]) gmap[genre] = {{gross:[],roi:[],score:[]}};
    if (gross != null) gmap[genre].gross.push(gross);
    if (sc   != null) gmap[genre].score.push(sc);
    if (gross != null && budget != null && budget > 0) {{
      const roi = (gross-budget)/budget*100;
      if (roi <= 1000) gmap[genre].roi.push(roi);   // mirror Python 1000% cap
    }}
  }});
  const avg = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;
  return Object.entries(gmap)
    .filter(([,v]) => v.score.length>=5 || v.gross.length>=5)
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
      plugins:{{
        legend:{{ display:true, position:"top", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12 }} }},
      }},
      scales:{{ y:{{ title:{{ display:true, text:"Films", color:"#8892a4", font:{{ size:11 }} }} }} }}
    }})
  }});
  bindExternalTooltip(C.movies, (dp) => ({{
    title: dp.label,
    value: `${{dp.dataset.label}}: ${{dp.formattedValue}}`,
    films: D.top_by_year?.[parseInt(dp.label)]?.score,
    fmt: v => `★${{v}}`,
  }}));

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
      scales:{{ y:{{ title:{{ display:true, text:"IMDB score", color:"#8892a4", font:{{ size:11 }} }}, suggestedMin:5, suggestedMax:8 }} }}
    }})
  }});
  bindExternalTooltip(C.scores, (dp) => ({{
    title: dp.label,
    value: `★${{dp.formattedValue}}`,
    films: D.top_by_year?.[parseInt(dp.label)]?.score,
    fmt: v => `★${{v}}`,
  }}));

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
  bindExternalTooltip(C.gross, (dp) => ({{
    title: dp.label,
    value: `$${{dp.formattedValue}}M`,
    films: D.top_by_year?.[parseInt(dp.label)]?.gross,
    fmt: v => `$${{v}}M`,
  }}));
}}

// ── FINANCIAL ────────────────────────────────────────────────────────────────

function initFinancial() {{
  const GENRES = D.top8_genres;

  // Deterministic per-film jitter based on title hash — breaks up vertical striping
  // at round-number budget milestones without altering underlying data meaning
  function seededJitter(title) {{
    let h = 0;
    for (let i = 0; i < title.length; i++) h = (Math.imul(31, h) + title.charCodeAt(i)) | 0;
    return ((h >>> 1) / 0x7FFFFFFF - 0.5) * 0.05; // ±2.5% spread on x-axis
  }}

  function scatterPts(g, lo, hi) {{
    return D.scatter
      .filter(d => d.g===g && d.yr>=lo && d.yr<=hi && d.x>0 && d.y>0)
      .map(d => ({{
        x:  d.x * (1 + seededJitter(d.t)),  // jittered display x
        ox: d.x,                              // original budget for tooltip
        y:  d.y, t: d.t, r: d.r
      }}));
  }}

  // Scatter: budget vs gross — all data shown via log scale
  const scatterDatasets = GENRES.map((g,i) => {{
    const pts = scatterPts(g, activeMin, activeMax);
    return {{
      label: `${{g}} (${{pts.length}})`,
      type: "scatter",
      data: pts,
      backgroundColor: COLORS[i]+"2e",   // ~18% opacity → density shows as darker clusters
      pointRadius: 3,
      pointHoverRadius: 7,
    }};
  }});
  // break-even line spanning the full log range
  scatterDatasets.push({{
    label: "Break-even",
    type: "line",
    data: [{{x:0.5,y:0.5}},{{x:6000,y:6000}}],
    borderColor:"#5a5d6a", borderWidth:1.5,
    borderDash:[6,4], pointRadius:0, fill:false,
  }});

  // Stash scatterPts for applyYearFilter (closure captures seededJitter too)
  initFinancial._scatterPts = scatterPts;

  // Log-scale tick labels — only show clean milestones
  const logTick = v => {{
    const clean = [0.5,1,2,5,10,20,50,100,200,500,1000,2000,5000];
    if (!clean.includes(v)) return '';
    return v >= 1000 ? `$${{(v/1000).toFixed(v>=2000?1:0)}}B` : `$${{v}}M`;
  }};

  C.scatter = new Chart(document.getElementById("cScatter"), {{
    type:"scatter",
    data:{{ datasets: scatterDatasets }},
    options: merge(DEF, {{
      plugins: {{
        legend: {{ position:"bottom", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12 }} }},
      }},
      scales: {{
        x: {{
          type: 'logarithmic',
          title: {{ display:true, text:"Budget (USD millions · log scale · ±2.5% jitter to reduce overplotting)", color:"#8892a4", font:{{ size:10 }} }},
          ticks: {{ color:"#8892a4", font:{{ size:10 }}, callback: logTick }},
          grid: {{ color:"#2a2d3a" }}
        }},
        y: {{
          type: 'logarithmic',
          title: {{ display:true, text:"Gross (USD millions · log scale · darker = denser cluster)", color:"#8892a4", font:{{ size:11 }} }},
          ticks: {{ color:"#8892a4", font:{{ size:10 }}, callback: logTick }},
          grid: {{ color:"#2a2d3a" }}
        }}
      }}
    }})
  }});
  bindExternalTooltip(C.scatter, (dp) => {{
    const raw = dp.raw;
    if (!raw?.t) return {{ title: 'Break-even', value: '', films: null, fmt: null }};
    return {{
      title: raw.t,
      value: `Budget $${{raw.ox}}M · Gross $${{raw.y}}M · ROI ${{raw.r}}%`,
      films: null,
      fmt: null,
    }};
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
          title:{{ display:true, text:"Avg ROI (%)", color:"#8892a4", font:{{ size:11 }} }},
          ticks:{{ callback: v => v+'%' }},
          suggestedMin: -50,
          suggestedMax: 300,
          grid:{{ color: ctx => ctx.tick.value===0 ? "#4a4d5a" : "#2a2d3a" }}
        }}
      }}
    }})
  }});
  bindExternalTooltip(C.roi, (dp) => ({{
    title: dp.label,
    value: `${{dp.formattedValue}}%`,
    films: D.top_by_year?.[parseInt(dp.label)]?.roi,
    fmt: v => `${{Math.round(v)}}%`,
  }}));

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
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true, fmt:v=>`$${{Math.round(v)}}M` }},
      }},
      scales:{{ x:{{ title:{{ display:true, text:"USD millions", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:11 }} }} }} }}
    }})
  }});
  bindExternalTooltip(C.genreGross, (dp) => ({{
    title: dp.label,
    value: `$${{dp.formattedValue}}M avg gross`,
    films: D.top_by_genre?.[dp.label]?.gross,
    fmt: v => `$${{v}}M`,
  }}));
}}

// ── GENRE ────────────────────────────────────────────────────────────────────

function initGenre() {{
  const gp = getGenreProf(activeMin, activeMax);
  // Genre ROI — green/red bars + value labels
  const gpROI = [...gp].sort((a,b)=>b.avg_roi-a.avg_roi).slice(0,15);
  // Use rank-based alpha so all bars remain clearly visible regardless of value spread
  C.genreROI = new Chart(document.getElementById("cGenreROI"), {{
    type:"bar",
    data:{{ labels:gpROI.map(d=>d.genre), datasets:[{{
      label:"Avg ROI %",
      data:gpROI.map(d=>d.avg_roi),
      backgroundColor: gpROI.map((d,i) => {{
        const alpha = 0.9 - 0.4*(i/Math.max(gpROI.length-1,1));
        return d.avg_roi>=0 ? `rgba(89,161,79,${{alpha.toFixed(2)}})` : `rgba(225,87,89,${{alpha.toFixed(2)}})`;
      }}),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true, fmt:v=>`${{Math.round(v)}}%` }},
      }},
      scales:{{
        x:{{ title:{{ display:true, text:"Avg ROI (%)", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0, callback:v=>v+'%' }}, grid:{{ color: ctx=>ctx.tick.value===0?"#4a4d5a":"#2a2d3a" }} }},
        y:{{ ticks:{{ font:{{ size:11 }} }} }}
      }}
    }})
  }});
  bindExternalTooltip(C.genreROI, (dp) => ({{
    title: dp.label,
    value: `${{dp.formattedValue}}% avg ROI`,
    films: D.top_by_genre?.[dp.label]?.roi,
    fmt: v => `${{Math.round(v)}}%`,
  }}));

  // Genre avg score — colored by score bucket
  const gpScore = [...gp].sort((a,b)=>b.avg_score-a.avg_score).slice(0,15);
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
        valLabel:{{ show:true, fmt:v=>v.toFixed(1) }},
      }},
      scales:{{ x:{{ suggestedMin:0, suggestedMax:9, title:{{ display:true, text:"IMDB Score", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:11 }} }} }} }}
    }})
  }});
  bindExternalTooltip(C.genreScore, (dp) => ({{
    title: dp.label,
    value: `★${{dp.formattedValue}}`,
    films: D.top_by_genre?.[dp.label]?.score,
    fmt: v => `★${{v}}`,
  }}));

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
      plugins:{{
        legend:{{ display:true, position:"bottom", labels:{{ color:"#8892a4", font:{{ size:11 }}, boxWidth:12 }} }},
      }},
      scales:{{ y:{{ title:{{ display:true, text:"Films per year", color:"#8892a4", font:{{ size:11 }} }}, stacked:false }} }}
    }})
  }});
  bindExternalTooltip(C.genreTrends, (dp) => {{
    const g = dp.dataset.label;
    const yr = parseInt(dp.label);
    return {{
      title: `${{g}} · ${{dp.label}}`,
      value: `${{dp.formattedValue}} films`,
      films: D.top_by_genre_year?.[g]?.[yr],
      fmt: v => `★${{v}}`,
    }};
  }});
}}

// ── ENGAGEMENT ───────────────────────────────────────────────────────────────

function engPts(lo, hi) {{
  return D.engagement
    .filter(d=>d.yr>=lo&&d.yr<=hi)
    .map(d => ({{ x:d.x, y:d.y, t:d.t, yr:d.yr, _c:scoreColor(d.x,0.6) }}));
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
      plugins:{{ legend:{{ display:false }} }},
      scales:{{
        x:{{ title:{{ display:true, text:"IMDB Score  ( green ≥ 7.5 · blue 6.5–7.5 · yellow 5–6.5 · red < 5 )", color:"#8892a4", font:{{ size:10 }} }}, min:1, max:10 }},
        y:{{ title:{{ display:true, text:"Votes (thousands)", color:"#8892a4", font:{{ size:11 }} }}, suggestedMin:0, suggestedMax:2500 }}
      }}
    }})
  }});
  bindExternalTooltip(C.engagement, (dp) => {{
    const raw = dp.raw;
    return {{
      title: raw.t,
      value: `★${{raw.x}} · ${{(raw.y*1000).toLocaleString()}} votes · ${{raw.yr || '—'}}`,
      films: null,
      fmt: null,
    }};
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
        valLabel:{{ show:true }},
      }},
      scales:{{
        x:{{ title:{{ display:true, text:"IMDB Score", color:"#8892a4", font:{{ size:11 }} }}, ticks:{{ maxRotation:0 }} }},
        y:{{ title:{{ display:true, text:"Film count", color:"#8892a4", font:{{ size:11 }} }}, suggestedMin:0 }}
      }}
    }})
  }});
  bindExternalTooltip(C.scoreDist, (dp) => ({{
    title: `Score ${{dp.label}}`,
    value: `${{dp.formattedValue}} films`,
    films: D.top_by_score_bin?.[dp.label],
    fmt: v => `★${{v}}`,
  }}));

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
      }}
    }})
  }});
  const crTotal = cr.reduce((s,d)=>s+d[1],0);
  bindExternalTooltip(C.contentRating, (dp) => ({{
    title: dp.label,
    value: `${{dp.formattedValue}} films (${{Math.round(dp.raw/crTotal*100)}}%)`,
    films: D.top_by_rating?.[dp.label],
    fmt: v => `★${{v}}`,
  }}));
}}

// ── KEYWORDS — dynamic helpers ────────────────────────────────────────────────

function getKwData(lo, hi) {{
  const freq = {{}}, ss = {{}}, sc = {{}};
  for (const [kw, yrs] of Object.entries(D.kw_year_data)) {{
    let c=0, s=0, n=0;
    for (let yr=lo; yr<=hi; yr++) {{
      const d = yrs[yr]; if (d) {{ c+=d[0]; s+=d[1]; n+=d[2]; }}
    }}
    if (c > 0) {{ freq[kw]=c; ss[kw]=s; sc[kw]=n; }}
  }}
  const byFreq = Object.entries(freq).sort((a,b)=>b[1]-a[1]).slice(0,20)
    .map(([kw,cnt]) => [kw, cnt]);
  const byScore = Object.entries(freq)
    .filter(([kw,cnt]) => cnt >= 3)
    .map(([kw,cnt]) => [kw, sc[kw] ? +(ss[kw]/sc[kw]).toFixed(2) : 0, cnt])
    .sort((a,b) => b[1]-a[1]).slice(0,20);
  return {{ freq: byFreq, score: byScore }};
}}

function getCountryData(lo, hi) {{
  return Object.entries(D.country_year_data).map(([ct, yrs]) => {{
    let c=0;
    for (let yr=lo; yr<=hi; yr++) c += (yrs[yr]||0);
    return [ct, c];
  }}).filter(d=>d[1]>0).sort((a,b)=>b[1]-a[1]);
}}

// ── KEYWORDS ─────────────────────────────────────────────────────────────────

function initKeywords() {{
  const kd  = getKwData(activeMin, activeMax);
  const ctd = getCountryData(activeMin, activeMax);

  // Keyword frequency — fading blue bars by rank
  C.kwFreq = new Chart(document.getElementById("cKwFreq"), {{
    type:"bar",
    data:{{ labels:kd.freq.map(d=>d[0]), datasets:[{{
      label:"Appearances", data:kd.freq.map(d=>d[1]),
      backgroundColor: kd.freq.map((_,i)=>`rgba(78,121,167,${{(0.9-0.5*i/Math.max(kd.freq.length,1)).toFixed(2)}})` ),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true }},
      }},
      scales:{{ x:{{ title:{{ display:true, text:"Film count", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }}
    }})
  }});
  bindExternalTooltip(C.kwFreq, (dp) => ({{
    title: dp.label,
    value: `${{dp.formattedValue}} films`,
    films: D.top_by_kw?.[dp.label],
    fmt: v => `★${{v}}`,
  }}));

  // Keyword score — colored by score bucket
  C.kwScore = new Chart(document.getElementById("cKwScore"), {{
    type:"bar",
    data:{{ labels:kd.score.map(d=>d[0]), datasets:[{{
      label:"Avg IMDB Score", data:kd.score.map(d=>d[1]),
      backgroundColor: kd.score.map(d=>scoreColor(d[1], 0.85)),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true, fmt:v=>v.toFixed(1) }},
      }},
      scales:{{ x:{{ min:0, max:9, title:{{ display:true, text:"IMDB Score", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }}
    }})
  }});
  bindExternalTooltip(C.kwScore, (dp) => ({{
    title: dp.label,
    value: `★${{dp.formattedValue}} avg score`,
    films: D.top_by_kw?.[dp.label],
    fmt: v => `★${{v}}`,
  }}));

  // Country production — fading teal bars
  C.countries = new Chart(document.getElementById("cCountries"), {{
    type:"bar",
    data:{{ labels:ctd.map(d=>d[0]), datasets:[{{
      label:"Films", data:ctd.map(d=>d[1]),
      backgroundColor: ctd.map((_,i)=>`rgba(89,161,79,${{(0.9-0.5*i/Math.max(ctd.length,1)).toFixed(2)}})` ),
      borderRadius:4,
    }}] }},
    options:merge(DEF, {{
      indexAxis:"y",
      plugins:{{
        legend:{{ display:false }},
        valLabel:{{ show:true }},
      }},
      scales:{{ x:{{ title:{{ display:true, text:"Film count", color:"#8892a4", font:{{ size:10 }} }}, ticks:{{ maxRotation:0 }} }}, y:{{ ticks:{{ font:{{ size:10 }} }} }} }}
    }})
  }});
  bindExternalTooltip(C.countries, (dp) => ({{
    title: dp.label,
    value: `${{dp.formattedValue}} films`,
    films: D.top_by_country?.[dp.label],
    fmt: v => `★${{v}}`,
  }}));
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
      const FILM_LIMIT = 8;
      const shown = d.films.slice(0, FILM_LIMIT);
      const extra = d.films.length - FILM_LIMIT;
      const extraRow = extra > 0
        ? `<tr><td colspan="4" style="text-align:center;color:var(--muted);font-style:italic;padding:6px 10px">… and ${{extra}} more film${{extra===1?'':'s'}}</td></tr>`
        : '';
      filmTr.innerHTML=`<td colspan="6"><div class="filmography-inner"><table><thead><tr><th>Title</th><th class="num">Year</th><th class="num">Score</th><th class="num">Gross</th></tr></thead><tbody>${{shown.map(f=>`<tr><td>${{f.t}}</td><td class="num">${{f.y||"—"}}</td><td class="num">${{f.s??"—"}}</td><td class="num">${{f.g!=null?fmtGross(f.g):"—"}}</td></tr>`).join("")}}${{extraRow}}</tbody></table></div></td>`;
      tr.after(filmTr); expandedRow={{dataRow:tr,filmRow:filmTr}};
    }});
    tbody.appendChild(tr);
  }});
}}

function refresh() {{ showLoading(()=>{{ filteredList=buildFilteredList(); renderTable(); }}); }}

let searchTimer;
document.getElementById("dirSearch").addEventListener("input", e => {{ filterText=e.target.value.toLowerCase().trim(); currentPage=0; clearTimeout(searchTimer); searchTimer=setTimeout(refresh,80); }});
document.querySelectorAll("#dirSortBtns .sort-btn").forEach(btn => {{ btn.addEventListener("click",()=>{{ document.querySelectorAll("#dirSortBtns .sort-btn").forEach(b=>b.classList.remove("active")); btn.classList.add("active"); sortKey=btn.dataset.sort; currentPage=0; refresh(); }}); }});
document.getElementById("pagePrev").addEventListener("click",()=>{{ if(currentPage>0){{currentPage--;refresh();}} }});
document.getElementById("pageNext").addEventListener("click",()=>{{ const t=Math.ceil(filteredList.length/PAGE_SIZE); if(currentPage<t-1){{currentPage++;refresh();}} }});

// ── SUB-TAB NAVIGATION ───────────────────────────────────────────────────────

let activeSubTab = "directors";

function showSubTab(name) {{
  activeSubTab = name;
  document.querySelectorAll(".sub-tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".sub-tab").forEach(b => b.classList.remove("active"));
  document.getElementById("sub-"+name).classList.add("active");
  document.querySelector(`[data-subtab="${{name}}"]`).classList.add("active");
  if (name==="directors") {{ filteredList=buildFilteredList(); renderTable(); }}
  if (name==="cast") {{ actorFilteredList=buildActorFilteredList(); renderActorTable(); }}
  if (name==="films") {{ filmFilteredList=buildFilmFilteredList(); renderFilmTable(); }}
}}

document.querySelectorAll(".sub-tab").forEach(btn => {{
  btn.addEventListener("click", () => showSubTab(btn.dataset.subtab));
}});

function initDirectorsPage() {{
  filteredList = buildFilteredList(); renderTable();
  actorFilteredList = buildActorFilteredList();
  filmFilteredList = buildFilmFilteredList();
  populateFilmGenreFilter();
}}

// ── ACTOR LEADERBOARD ─────────────────────────────────────────────────────────

let actorSortKey = "gross", actorFilterText = "", actorCurrentPage = 0;
let actorExpandedRow = null, actorFilteredList = [];

const ROLE_LABELS = {{ 1: "Lead", 2: "Supporting", 3: "Featured" }};
function rolePill(r) {{
  const lbl = ROLE_LABELS[r] || "—";
  const cls = r===1 ? "lead" : r===2 ? "support" : "featured";
  return `<span class="role-pill ${{cls}}">${{lbl}}</span>`;
}}

function buildActorFilteredList() {{
  let list = D.actors.map(a => {{
    const films = a.films.filter(f => f.y>=activeMin && f.y<=activeMax);
    if (!films.length) return null;
    const sc = films.map(f=>f.s).filter(Boolean);
    const gr = films.map(f=>f.g).filter(v=>v!=null);
    const best = films.reduce((x,y)=>((y.s||0)>(x.s||0)?y:x));
    return {{ name:a.name, count:films.length, avg_score:sc.length?Math.round(sc.reduce((x,y)=>x+y,0)/sc.length*100)/100:null, total_gross:gr.length?Math.round(gr.reduce((x,y)=>x+y,0)*10)/10:0, best:best.t, films }};
  }}).filter(a => a && a.name.toLowerCase().includes(actorFilterText));

  if (actorSortKey==="gross") list.sort((a,b)=>(b.total_gross||0)-(a.total_gross||0));
  if (actorSortKey==="score") list.sort((a,b)=>(b.avg_score||0)-(a.avg_score||0));
  if (actorSortKey==="count") list.sort((a,b)=>b.count-a.count);
  return list;
}}

function showActorLoading(then) {{
  const ov=document.getElementById("actorLoading"); ov.classList.add("visible");
  requestAnimationFrame(()=>requestAnimationFrame(()=>{{ then(); ov.classList.remove("visible"); }}));
}}

function renderActorTable() {{
  const tbody=document.getElementById("actorTbody");
  const pInfo=document.getElementById("actorPageInfo"), pInd=document.getElementById("actorPageIndicator");
  const btnPrev=document.getElementById("actorPagePrev"), btnNext=document.getElementById("actorPageNext");
  tbody.innerHTML=""; actorExpandedRow=null;

  const totalPages=Math.max(1,Math.ceil(actorFilteredList.length/PAGE_SIZE));
  if (actorCurrentPage>=totalPages) actorCurrentPage=totalPages-1;
  const start=actorCurrentPage*PAGE_SIZE;
  const items=actorFilteredList.slice(start, start+PAGE_SIZE);

  pInd.textContent=`Page ${{actorCurrentPage+1}} of ${{totalPages}}`;
  pInfo.textContent=actorFilteredList.length===0?"No actors found":`Showing ${{start+1}}–${{Math.min(start+PAGE_SIZE,actorFilteredList.length)}} of ${{actorFilteredList.length}} actors`;
  btnPrev.disabled=actorCurrentPage===0; btnNext.disabled=actorCurrentPage>=totalPages-1;

  if (!actorFilteredList.length) {{ tbody.innerHTML=`<tr><td colspan="6" class="no-results">No actors match.</td></tr>`; return; }}

  items.forEach((a,i) => {{
    const tr=document.createElement("tr"); tr.className="dir-row";
    tr.innerHTML=`<td><span class="rank-num">${{start+i+1}}</span></td><td><strong>${{a.name}}</strong></td><td class="num">${{a.count}}</td><td class="num">${{a.avg_score!=null?`<span class="score-pill">${{a.avg_score}}</span>`:"—"}}</td><td class="num">${{fmtGross(a.total_gross)}}</td><td><span class="best-film" title="${{a.best}}">${{a.best}}</span></td>`;

    tr.addEventListener("click", () => {{
      if (actorExpandedRow&&actorExpandedRow.dataRow!==tr) {{ actorExpandedRow.filmRow.remove(); actorExpandedRow.dataRow.classList.remove("expanded"); actorExpandedRow=null; }}
      if (actorExpandedRow&&actorExpandedRow.dataRow===tr) {{ actorExpandedRow.filmRow.remove(); tr.classList.remove("expanded"); actorExpandedRow=null; return; }}
      tr.classList.add("expanded");
      const filmTr=document.createElement("tr"); filmTr.className="filmography-row";
      const FILM_LIMIT = 8;
      const shown = a.films.slice(0, FILM_LIMIT);
      const extra = a.films.length - FILM_LIMIT;
      const extraRow = extra > 0
        ? `<tr><td colspan="5" style="text-align:center;color:var(--muted);font-style:italic;padding:6px 10px">+ ${{extra}} more</td></tr>`
        : '';
      filmTr.innerHTML=`<td colspan="6"><div class="filmography-inner"><table><thead><tr><th class="num">Year</th><th>Title</th><th>Role</th><th class="num">Score</th><th class="num">Gross</th></tr></thead><tbody>${{shown.map(f=>`<tr><td class="num">${{f.y||"—"}}</td><td>${{f.t}}</td><td>${{rolePill(f.r)}}</td><td class="num">${{f.s??"—"}}</td><td class="num">${{f.g!=null?fmtGross(f.g):"—"}}</td></tr>`).join("")}}${{extraRow}}</tbody></table></div></td>`;
      tr.after(filmTr); actorExpandedRow={{dataRow:tr,filmRow:filmTr}};
    }});
    tbody.appendChild(tr);
  }});
}}

function refreshActor() {{ showActorLoading(()=>{{ actorFilteredList=buildActorFilteredList(); renderActorTable(); }}); }}

let actorSearchTimer;
document.getElementById("actorSearch").addEventListener("input", e => {{ actorFilterText=e.target.value.toLowerCase().trim(); actorCurrentPage=0; clearTimeout(actorSearchTimer); actorSearchTimer=setTimeout(refreshActor,80); }});
document.querySelectorAll("#actorSortBtns .sort-btn").forEach(btn => {{ btn.addEventListener("click",()=>{{ document.querySelectorAll("#actorSortBtns .sort-btn").forEach(b=>b.classList.remove("active")); btn.classList.add("active"); actorSortKey=btn.dataset.sort; actorCurrentPage=0; refreshActor(); }}); }});
document.getElementById("actorPagePrev").addEventListener("click",()=>{{ if(actorCurrentPage>0){{actorCurrentPage--;refreshActor();}} }});
document.getElementById("actorPageNext").addEventListener("click",()=>{{ const t=Math.ceil(actorFilteredList.length/PAGE_SIZE); if(actorCurrentPage<t-1){{actorCurrentPage++;refreshActor();}} }});

// ── FILM LEADERBOARD ──────────────────────────────────────────────────────────

const FILM_PAGE_SIZE = 50;
let filmSortKey = "score", filmSortAsc = false, filmFilterText = "";
let filmGenreFilter = "", filmRatingFilter = "";
let filmCurrentPage = 0, filmFilteredList = [];

function populateFilmGenreFilter() {{
  const sel = document.getElementById("filmGenreFilter");
  if (sel.options.length > 1) return;
  const genres = [...new Set(D.films.map(f=>f.genre))].sort();
  genres.forEach(g => {{
    const opt = document.createElement("option");
    opt.value = g; opt.textContent = g;
    sel.appendChild(opt);
  }});
}}

function buildFilmFilteredList() {{
  let list = D.films.filter(f => {{
    if (f.y < activeMin || f.y > activeMax) return false;
    if (filmGenreFilter && f.genre !== filmGenreFilter) return false;
    if (filmRatingFilter && f.rating !== filmRatingFilter) return false;
    const q = filmFilterText;
    if (q && !f.t.toLowerCase().includes(q) && !(f.director||"").toLowerCase().includes(q)) return false;
    return true;
  }});

  const dir = filmSortAsc ? 1 : -1;
  const cmp = (a,b) => {{
    if (filmSortKey==="score")  return dir * ((a.s||0)-(b.s||0));
    if (filmSortKey==="gross")  return dir * ((a.g||0)-(b.g||0));
    if (filmSortKey==="budget") return dir * ((a.b||0)-(b.b||0));
    if (filmSortKey==="roi")    return dir * ((a.r||0)-(b.r||0));
    if (filmSortKey==="year")   return dir * ((a.y||0)-(b.y||0));
    if (filmSortKey==="title")  return dir * a.t.localeCompare(b.t);
    return 0;
  }};
  list.sort(cmp);
  return list;
}}

function fmtROI(v) {{ return v!=null ? `${{v>=0?"+":""}}${{v.toFixed(0)}}%` : "—"; }}

function showFilmLoading(then) {{
  const ov=document.getElementById("filmLoading"); ov.classList.add("visible");
  requestAnimationFrame(()=>requestAnimationFrame(()=>{{ then(); ov.classList.remove("visible"); }}));
}}

function renderFilmTable() {{
  const tbody=document.getElementById("filmTbody");
  const pInfo=document.getElementById("filmPageInfo"), pInd=document.getElementById("filmPageIndicator");
  const btnPrev=document.getElementById("filmPagePrev"), btnNext=document.getElementById("filmPageNext");
  tbody.innerHTML="";

  const totalPages=Math.max(1,Math.ceil(filmFilteredList.length/FILM_PAGE_SIZE));
  if (filmCurrentPage>=totalPages) filmCurrentPage=totalPages-1;
  const start=filmCurrentPage*FILM_PAGE_SIZE;
  const items=filmFilteredList.slice(start, start+FILM_PAGE_SIZE);

  pInd.textContent=`Page ${{filmCurrentPage+1}} of ${{totalPages}}`;
  pInfo.textContent=filmFilteredList.length===0?"No films found":`Showing ${{start+1}}–${{Math.min(start+FILM_PAGE_SIZE,filmFilteredList.length)}} of ${{filmFilteredList.length}} films`;
  btnPrev.disabled=filmCurrentPage===0; btnNext.disabled=filmCurrentPage>=totalPages-1;

  if (!filmFilteredList.length) {{ tbody.innerHTML=`<tr><td colspan="9" class="no-results">No films match.</td></tr>`; return; }}

  const topScore = Math.max(...filmFilteredList.map(f=>f.s||0));
  const topGross = Math.max(...filmFilteredList.filter(f=>f.g!=null).map(f=>f.g), 0);
  const topBudget = Math.max(...filmFilteredList.filter(f=>f.b!=null).map(f=>f.b), 0);
  const topROI = Math.max(...filmFilteredList.filter(f=>f.r!=null).map(f=>f.r), -Infinity);

  items.forEach(f => {{
    const tr=document.createElement("tr");
    const scCls = f.s===topScore && topScore>0 ? " col-top" : "";
    const gCls  = f.g!=null && f.g===topGross && topGross>0 ? " col-top" : "";
    const bCls  = f.b!=null && f.b===topBudget && topBudget>0 ? " col-top" : "";
    const rCls  = f.r!=null && f.r===topROI ? " col-top" : "";
    tr.innerHTML=`
      <td><span class="film-title" title="${{f.t}}">${{f.t}}</span></td>
      <td class="num">${{f.y||"—"}}</td>
      <td>${{f.genre}}</td>
      <td>${{f.director||"—"}}</td>
      <td>${{f.rating}}</td>
      <td class="num${{scCls}}">${{f.s!=null?f.s:"—"}}</td>
      <td class="num${{gCls}}">${{f.g!=null?fmtGross(f.g):"—"}}</td>
      <td class="num${{bCls}}">${{f.b!=null?fmtGross(f.b):"—"}}</td>
      <td class="num${{rCls}}">${{fmtROI(f.r)}}</td>`;
    tbody.appendChild(tr);
  }});
}}

function refreshFilm() {{ showFilmLoading(()=>{{ filmFilteredList=buildFilmFilteredList(); renderFilmTable(); }}); }}

let filmSearchTimer;
document.getElementById("filmSearch").addEventListener("input", e => {{ filmFilterText=e.target.value.toLowerCase().trim(); filmCurrentPage=0; clearTimeout(filmSearchTimer); filmSearchTimer=setTimeout(refreshFilm,80); }});
document.getElementById("filmGenreFilter").addEventListener("change", e => {{ filmGenreFilter=e.target.value; filmCurrentPage=0; refreshFilm(); }});
document.getElementById("filmRatingFilter").addEventListener("change", e => {{ filmRatingFilter=e.target.value; filmCurrentPage=0; refreshFilm(); }});
document.querySelectorAll(".film-sort-btn").forEach(btn => {{ btn.addEventListener("click",()=>{{ document.querySelectorAll(".film-sort-btn").forEach(b=>b.classList.remove("active")); btn.classList.add("active"); filmSortKey=btn.dataset.fsort; filmCurrentPage=0; refreshFilm(); }}); }});
document.getElementById("filmSortDir").addEventListener("click", () => {{
  filmSortAsc = !filmSortAsc;
  document.getElementById("filmSortDir").textContent = filmSortAsc ? "\u2191" : "\u2193";
  filmCurrentPage=0; refreshFilm();
}});
document.getElementById("filmPagePrev").addEventListener("click",()=>{{ if(filmCurrentPage>0){{filmCurrentPage--;refreshFilm();}} }});
document.getElementById("filmPageNext").addEventListener("click",()=>{{ const t=Math.ceil(filmFilteredList.length/FILM_PAGE_SIZE); if(filmCurrentPage<t-1){{filmCurrentPage++;refreshFilm();}} }});

// ── Chart info popups ────────────────────────────────────────────────────────

const CHART_INFO = {{
  cMovies: {{
    why: "Bar chart chosen to make discrete annual counts instantly comparable year-to-year. An orange rolling-average line (5-yr window) is overlaid to separate long-run structural trends from year-to-year noise.",
    what: "Reveals production-volume booms and contractions across decades — peaks often align with studio-system expansions, streaming-era transitions, or blockbuster supercycles."
  }},
  cScores: {{
    why: "Line/area chart is the natural choice for a continuous metric measured at regular time intervals. Gradient fill gives depth without obscuring the trend line itself.",
    what: "Tests whether audience-perceived quality has improved, declined, or plateaued over time — a proxy for both evolving taste and potential rating inflation/deflation on IMDB."
  }},
  cGross: {{
    why: "Area chart with billion-scale Y-axis captures the enormous magnitude range of box-office revenue. The gradient fill emphasises cumulative industry growth rather than individual spikes.",
    what: "Shows the financial scale of Hollywood's expansion. Sharp spikes pinpoint blockbuster years; the overall slope indicates whether the industry's revenue base is growing or plateauing."
  }},
  cScatter: {{
    why: "Scatter plot chosen to expose the budget → gross relationship. Three expert-recommended techniques improve readability at scale: (1) Log scale on both axes — shows the full range ($0.5M indie to $300M+ blockbuster) without clipping. (2) ~18% opacity — overlapping dots accumulate into a heat-map effect revealing where most films cluster. (3) ±2.5% seeded jitter on x — breaks vertical striping from round-number budgets; deterministic so the chart is stable across loads and filter changes. Data scope: US productions only. Non-US films record budgets in local currency (JPY, EUR, INR, etc.) while gross is US domestic USD — comparing them produces nonsensical ROI (e.g. a ¥2.35B Japanese budget appears as $2.35B, inflating ROI ~100×). A $400M budget ceiling and extreme-ratio check remove remaining data-entry errors.",
    what: "Reveals whether larger US film budgets reliably produce larger returns, which genres consistently clear the break-even diagonal, and where the bulk of productions cluster on the cost/revenue spectrum."
  }},
  cROI: {{
    why: "Line/area chart with a highlighted zero-line makes the profitable-vs-loss boundary instantly visible. Gradient fill reinforces the direction of trend. Data scope: US productions only — same constraint as the scatter chart to ensure budget and gross are in the same currency.",
    what: "Shows whether US film industry ROI improves over time, and which eras saw studios consistently over- or under-recouping their investments."
  }},
  cGenreGross: {{
    why: "Horizontal bar chart accommodates genre name labels without rotation, and opacity scaled to magnitude creates a visual hierarchy so top earners pop without needing to read exact values.",
    what: "Identifies which genres generate the most box-office revenue per film on average — useful for distinguishing high-investment blockbuster genres from lower-cost but popular ones."
  }},
  cGenreROI: {{
    why: "Green/red coloring with intensity scaled to magnitude means profitable vs unprofitable genres are scannable in under a second without reading any numbers. Horizontal layout fits long genre labels.",
    what: "Separates financially safe investments from risky ones. Low-budget genres often outperform on ROI even when their gross is modest — a key insight hidden in raw revenue charts."
  }},
  cGenreScore: {{
    why: "Score-bucket coloring (green → yellow → red) lets quality tier be read without touching the axis. Sorting by score surfaces the quality leaders at a glance.",
    what: "Reveals which genres earn critical and audience respect versus which are commercially driven but critically dismissed — a useful complement to the revenue-only view."
  }},
  cGenreTrends: {{
    why: "Multi-line area chart shows several genre series simultaneously; the translucent fills help distinguish overlap zones without fully obscuring other lines. Stacked area was avoided as it would misrepresent genre independence.",
    what: "Shows genre popularity cycles — which genres rose, peaked, and declined decade by decade, and which are on an upward trajectory in the most recent years visible."
  }},
  cEngagement: {{
    why: "Scatter plot is the standard tool for showing correlation between two continuous metrics. Per-point color coding (green ≥ 7.5 · blue 6.5–7.5 · yellow 5–6.5 · red < 5) adds a third dimension (quality) without a separate chart.",
    what: "Tests whether high-rated films are also widely voted on, or whether some niches earn great scores from small audiences — a distinction between visibility and quality."
  }},
  cScoreDist: {{
    why: "Histogram is the canonical tool for showing a distribution's shape, spread, and skew. Score-colored bars reinforce meaning at each quality tier so the chart is self-annotating.",
    what: "Shows whether most films cluster in a narrow 'good' range or span the full spectrum. The shape (normal, skewed, bimodal) reveals structural biases in what gets produced and rated."
  }},
  cRating: {{
    why: "Doughnut chart is ideal for part-of-whole relationships with a small number of categories (≤ 8). The hollow center lets proportions breathe and keeps focus on the arc lengths rather than raw counts.",
    what: "Shows how the dataset splits by audience certification — which age demographics dominate production and whether the industry skews toward broad-audience or restricted content."
  }},
  cKwFreq: {{
    why: "Horizontal ranked bars with fading opacity encode both frequency and rank visually. Horizontal layout is necessary to accommodate multi-word keyword phrases without truncation.",
    what: "Surfaces recurring narrative themes and plot elements across the entire dataset — a proxy for what stories the film industry keeps returning to."
  }},
  cKwScore: {{
    why: "Score-colored bars let quality signal be read at a glance without scanning the axis. Ranking by average score instead of frequency highlights thematic quality, not just volume.",
    what: "Identifies narrative elements that statistically co-occur with well-received films. These themes don't just appear often — they correlate with audience approval."
  }},
  cCountries: {{
    why: "Ranked horizontal bars with opacity gradient visualise both volume and relative standing simultaneously. Country names fit cleanly on horizontal labels.",
    what: "Shows the geographic distribution of film production and exposes US dominance alongside which other national industries contribute meaningfully to the dataset."
  }},
}};

// ── Chart zoom modal ─────────────────────────────────────────────────────────

const CANVAS_TO_C = {{
  cMovies: 'movies', cScores: 'scores', cGross: 'gross',
  cScatter: 'scatter', cROI: 'roi', cGenreGross: 'genreGross',
  cGenreROI: 'genreROI', cGenreScore: 'genreScore', cGenreTrends: 'genreTrends',
  cEngagement: 'engagement', cScoreDist: 'scoreDist', cRating: 'contentRating',
  cKwFreq: 'kwFreq', cKwScore: 'kwScore', cCountries: 'countries',
}};
let zoomChart = null;

function openZoomModal(canvasId) {{
  const key = CANVAS_TO_C[canvasId];
  const src = key ? C[key] : null;
  if (!src) return;
  const card = document.getElementById(canvasId)?.closest('.chart-card');
  const title = card?.querySelector('.chart-title')?.textContent || 'Chart';
  document.getElementById('zoom-modal-title').textContent = title;
  const modal = document.getElementById('zoom-modal');
  modal.classList.add('visible');
  if (zoomChart) {{ zoomChart.destroy(); zoomChart = null; }}
  // src.options is a Chart.js Proxy — JSON.stringify fires its get-trap which
  // executes embedded formatter callbacks (fmt, fmtROI …) with wrong arg types.
  // Use the raw plain-object config instead, same pattern as bindExternalTooltip.
  const rawOpts = src.config._config.options || {{}};
  const opts = Object.assign({{}}, rawOpts, {{
    maintainAspectRatio: false,
    animation: false,
  }});
  const zoomCanvas = document.getElementById('zoom-canvas');
  zoomChart = new Chart(zoomCanvas, {{
    type: src.config.type,
    data: JSON.parse(JSON.stringify(src.data)),
    options: opts,
    plugins: src.config.plugins,
  }});
  zoomCanvas.addEventListener('mouseleave', hideChartTooltip);
}}

function closeZoomModal() {{
  document.getElementById('zoom-modal').classList.remove('visible');
  if (zoomChart) {{ zoomChart.destroy(); zoomChart = null; }}
}}

document.getElementById('zoom-modal-close').addEventListener('click', closeZoomModal);
document.getElementById('zoom-modal').addEventListener('click', e => {{
  if (e.target.id === 'zoom-modal') closeZoomModal();
}});
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closeZoomModal();
}});

// Inject info + zoom buttons and popups into every chart card
document.querySelectorAll('.chart-card').forEach(card => {{
  const canvas = card.querySelector('canvas');
  if (!canvas) return;
  const info = CHART_INFO[canvas.id];

  const btn = document.createElement('button');
  btn.className = 'chart-info-btn';
  btn.textContent = 'ⓘ';
  btn.title = 'Why this chart / What it shows';

  const zoomBtn = document.createElement('button');
  zoomBtn.className = 'chart-zoom-btn';
  zoomBtn.textContent = '\u2922';
  zoomBtn.title = 'Expand chart';
  zoomBtn.addEventListener('click', e => {{
    e.stopPropagation();
    openZoomModal(canvas.id);
  }});

  const actions = document.createElement('div');
  actions.className = 'chart-title-actions';
  if (info) actions.appendChild(btn);
  actions.appendChild(zoomBtn);

  const popup = document.createElement('div');
  popup.className = 'chart-info-popup';
  if (info) {{
    popup.innerHTML =
      `<div class="info-section"><div class="info-label">Why this visualization?</div><div class="info-text">${{info.why}}</div></div>` +
      `<div class="info-section"><div class="info-label">What it conveys</div><div class="info-text">${{info.what}}</div></div>`;
  }}

  // Wrap title + buttons in a row
  const titleEl = card.querySelector('.chart-title');
  const row = document.createElement('div');
  row.className = 'chart-title-row';
  titleEl.replaceWith(row);
  row.appendChild(titleEl);
  row.appendChild(actions);

  if (info) card.appendChild(popup);

  if (info) {{
    let hovering = false;

    btn.addEventListener('mouseenter', () => {{
      hovering = true;
      popup.classList.add('visible');
    }});

    btn.addEventListener('mouseleave', () => {{
      hovering = false;
      if (popup.dataset.pinned !== 'true') {{
        popup.classList.remove('visible');
        btn.classList.remove('active');
      }}
    }});

    btn.addEventListener('click', e => {{
      e.stopPropagation();
      if (popup.dataset.pinned === 'true') {{
        popup.removeAttribute('data-pinned');
        btn.classList.remove('active');
        if (!hovering) popup.classList.remove('visible');
      }} else {{
        document.querySelectorAll('.chart-info-popup').forEach(p => {{
          if (p !== popup) {{
            p.removeAttribute('data-pinned');
            p.classList.remove('visible');
          }}
        }});
        document.querySelectorAll('.chart-info-btn').forEach(b => {{
          if (b !== btn) b.classList.remove('active');
        }});
        popup.dataset.pinned = 'true';
        popup.classList.add('visible');
        btn.classList.add('active');
      }}
    }});
  }}
}});

document.addEventListener('click', () => {{
  document.querySelectorAll('.chart-info-popup').forEach(p => {{
    p.removeAttribute('data-pinned');
    p.classList.remove('visible');
  }});
  document.querySelectorAll('.chart-info-btn').forEach(b => b.classList.remove('active'));
}});

// ── Boot ──────────────────────────────────────────────────────────────────────

showPage("overview");
INIT.overview = true;
updateKPIs(activeMin, activeMax);
populateFilmGenreFilter();
filteredList = buildFilteredList(); renderTable();
actorFilteredList = buildActorFilteredList();
filmFilteredList = buildFilmFilteredList();

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
print(f"  Actors: {len(actor_stats):,}  |  Films: {len(films_list):,}")
unique_flags = sorted(set(_currency_flags))
print(f"\n  Currency sanity check — {len(unique_flags)} unique film(s) flagged and excluded from financial data:")
for f in unique_flags[:30]:
    print(f)
if len(unique_flags) > 30:
    print(f"  ... and {len(unique_flags)-30} more")
