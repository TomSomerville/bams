<p align="center"><img src="branding/logo/bams-wordmark.png" alt="BAMS — Your Personal Media Stream" width="420"></p>

# BAMS — Bad Ass Media Server

A self-hosted, Netflix/Plex-style server for **your own** movies, TV shows (and later, music).
Point it at folders on a local or mounted drive. It finds and identifies your media, pulls posters and
descriptions, and streams to any browser. It runs on **Windows** and **Debian / Ubuntu / Linux Mint**.

> **Status: prototype.** The web UI runs on mock data (fictional titles, locally generated art).
> The Python backend comes next. See [docs/PLAN.md](docs/PLAN.md) for the full plan.

## Try the UI prototype

Requires Node 20+.

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173.

## Layout

| Path | What |
|---|---|
| `docs/PLAN.md` | Architecture, how Plex works, metadata/licensing decisions, phases |
| `web/` | React + Vite + TypeScript UI (mock data in `web/src/mock/`) |
| `branding/logo/` | Logo files. `*-transparent.png` are cut-outs for dark backgrounds |
| `tools/mock_art/` | Regenerates the prototype's placeholder posters via a local ComfyUI |

## License

[MIT](LICENSE). Metadata providers have their own terms (see PLAN.md §5). BAMS uses the TMDB API but is not
endorsed or certified by TMDB. Plex is a trademark of Plex, Inc. BAMS is not affiliated with or endorsed by Plex.
