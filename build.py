"""Build a static Stremio addon into ./dist from The Movie Database."""

import json
import os
import random
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 365
PER_LANGUAGE = 30
PAGE_SIZE = 20
MIN_PER_LANGUAGE = 10
LISTS = [
    {"language": "hi", "region": "IN", "min_votes": 0},
    {"language": "en", "region": "IE", "min_votes": 50},
]

BASE = "https://api.themoviedb.org/3"
KINDS = ("series", "movie")
ENDPOINT = {"series": "tv", "movie": "movie"}
MAX_PAGES = 5
RETRIES = 3
RETRY_PAUSE = 2.0
REQUEST_PAUSE = 0.05
TIMEOUT = 30

ATTRIBUTION = (
    "This application uses TMDB and the TMDB APIs but is not endorsed, "
    "certified, or otherwise approved by TMDB."
)

MANIFEST = {
    "id": "io.github.better-stremio.whattowatchnext",
    "version": "1.0.0",
    "name": "What to watch next",
    "description": (
        "Hindi and English shows and movies, refreshed daily. "
        + ATTRIBUTION
    ),
    "resources": ["catalog"],
    "types": ["series", "movie"],
    "idPrefixes": ["tt"],
    "catalogs": [
        {
            "type": "series",
            "id": "wtwn",
            "name": "What to watch next",
            "extra": [{"name": "skip", "isRequired": False}],
        },
        {
            "type": "movie",
            "id": "wtwn",
            "name": "What to watch next",
            "extra": [{"name": "skip", "isRequired": False}],
        },
    ],
}


def fetch(api_key, path, params):
    """GET BASE + path with params plus api_key; return the parsed JSON.

    Retries up to RETRIES times, pausing RETRY_PAUSE seconds on HTTP 429,
    5xx or network errors. Error messages name only the path and status.
    """
    query = dict(params)
    query["api_key"] = api_key
    url = BASE + path + "?" + urllib.parse.urlencode(query)
    last_error = RuntimeError(f"request failed for {path}")
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "what-to-watch-next/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            time.sleep(REQUEST_PAUSE)
            return json.loads(data)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                last_error = RuntimeError(f"HTTP {exc.code} for {path}")
            else:
                raise RuntimeError(f"HTTP {exc.code} for {path}")
        except (urllib.error.URLError, OSError):
            last_error = RuntimeError(f"network error for {path}")
        if attempt < RETRIES - 1:
            time.sleep(RETRY_PAUSE)
    raise last_error


def make_meta(kind, item, imdb_id):
    date_field = "first_air_date" if kind == "series" else "release_date"
    meta = {
        "id": imdb_id,
        "type": kind,
        "name": item.get("name") if kind == "series" else item.get("title"),
        "poster": "https://image.tmdb.org/t/p/w500" + item["poster_path"],
    }
    backdrop = item.get("backdrop_path")
    if backdrop:
        meta["background"] = "https://image.tmdb.org/t/p/w1280" + backdrop
    overview = item.get("overview")
    if overview:
        meta["description"] = overview
    release = item.get(date_field)
    if release:
        meta["releaseInfo"] = release[:4]
    return meta


def build_kind(api_key, kind, today):
    """Collect usable titles for one kind; return (shuffled metas, per-language counts)."""
    endpoint = ENDPOINT[kind]
    date_field = "first_air_date" if kind == "series" else "primary_release_date"
    gte = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    lte = today.isoformat()
    seen = set()
    metas = []
    counts = {}
    for entry in LISTS:
        base_params = {
            date_field + ".gte": gte,
            date_field + ".lte": lte,
            "with_original_language": entry["language"],
            "watch_region": entry["region"],
            "with_watch_monetization_types": "flatrate",
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "vote_count.gte": str(entry["min_votes"]),
        }
        if kind == "series":
            base_params["without_genres"] = "10763,10764,10767"
        lang_metas = []
        for page in range(1, MAX_PAGES + 1):
            params = dict(base_params)
            params["page"] = str(page)
            data = fetch(api_key, f"/discover/{endpoint}", params)
            for item in data.get("results", []):
                if len(lang_metas) >= PER_LANGUAGE:
                    break
                if not item.get("poster_path"):
                    continue
                ext = fetch(api_key, f"/{endpoint}/{item['id']}/external_ids", {})
                imdb_id = ext.get("imdb_id") or ""
                if not imdb_id.startswith("tt") or imdb_id in seen:
                    continue
                seen.add(imdb_id)
                lang_metas.append(make_meta(kind, item, imdb_id))
            if len(lang_metas) >= PER_LANGUAGE:
                break
        if len(lang_metas) < MIN_PER_LANGUAGE:
            raise RuntimeError(
                f"{kind}: language {entry['language']} has only "
                f"{len(lang_metas)} usable titles"
            )
        counts[entry["language"]] = len(lang_metas)
        metas.extend(lang_metas)
    rng = random.Random(today.isoformat() + kind)
    rng.shuffle(metas)
    return metas, counts


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))


def write_dist(results):
    tmp = "dist.tmp"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    for kind in KINDS:
        os.makedirs(os.path.join(tmp, "catalog", kind, "wtwn"))
    write_json(os.path.join(tmp, "manifest.json"), MANIFEST)
    for kind in KINDS:
        metas = results[kind][0]
        total = len(metas)
        cat_dir = os.path.join(tmp, "catalog", kind)
        write_json(os.path.join(cat_dir, "wtwn.json"), {"metas": metas[:PAGE_SIZE]})
        n = 0
        while True:
            write_json(
                os.path.join(cat_dir, "wtwn", f"skip={n}.json"),
                {"metas": metas[n:n + PAGE_SIZE]},
            )
            if n >= total:
                break
            n += PAGE_SIZE
    with open(os.path.join(tmp, ".nojekyll"), "w", encoding="utf-8"):
        pass
    with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
        f.write(
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>What to watch next</title></head><body>"
            "<p>What to watch next, a Stremio addon.</p>"
            f"<p><img src=\"tmdb.svg\" alt=\"TMDB\" height=\"16\"> {ATTRIBUTION}</p></body></html>\n"
        )
    shutil.copy("tmdb.svg", os.path.join(tmp, "tmdb.svg"))
    if os.path.isdir("dist"):
        shutil.rmtree("dist")
    os.replace(tmp, "dist")


def main():
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        print("TMDB_API_KEY is not set", file=sys.stderr)
        sys.exit(1)
    today = datetime.now(timezone.utc).date()
    results = {}
    for kind in KINDS:
        results[kind] = build_kind(api_key, kind, today)
    write_dist(results)
    for kind in KINDS:
        metas, counts = results[kind]
        print(f"{kind}: total={len(metas)}")
        for entry in LISTS:
            print(f"  {entry['language']}: {counts[entry['language']]}")
        print("  first 8: " + ", ".join(m["name"] for m in metas[:8]))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
