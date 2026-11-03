# What to watch next

A Stremio addon with two rows, Series and Movies: recent Hindi and English titles, shuffled together and rebuilt daily.

Install it by adding this address to Stremio:

    https://better-stremio.github.io/what-to-watch-next/manifest.json

## How it works

A scheduled GitHub Action runs `build.py`, which asks TMDB for popular titles from the last 12 months, then publishes the result as static files on GitHub Pages. English titles are ones streaming in Ireland and Hindi titles are ones streaming in India; change `LISTS` in `build.py` to adjust this. If a build fails, the last good lists stay online.

The generated lists are deployed directly to Pages and are not committed here. The build needs a `TMDB_API_KEY` repository secret.

This addon provides lists only, no streams.

## Attribution

This application uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.

<img src="tmdb.svg" alt="TMDB" height="16">
