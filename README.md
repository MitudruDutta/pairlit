# Pairlit

Pairlit is an agent dating experiment built from exactly two public sources per person: LinkedIn and public Instagram. It finds real public-facing creators through live search, verifies matching official accounts, builds evidence-backed profiles, lets separate agents converse, and produces directional rankings.

The Chemistry Lab shows both agents' independent assessments and lets the same pair meet in different settings. A high assessment from one agent cannot conceal a lower assessment from the other. These are fictional public-profile simulations, not claims that the depicted people participated or are romantically available.

## Run locally

1. Activate the Python environment:
   ```bash
   source ~/python/bin/activate
   ```
2. Install dependencies:
   ```bash
   python -m pip install -e '.[test]'
   cd apps/web
   npm ci
   npm run build
   cd ../..
   ```
3. Copy `.env.example` to `.env`. Set `APIFY_TOKEN` locally. Never commit credentials. Configure an extraction ceiling that fits your existing provider credits.
4. Start Ollama and install the configured model:
   ```bash
   ollama pull qwen3.5:4b
   ```
5. Start the website:
   ```bash
   PYTHONPATH=backend python -m pairlit.cli serve
   ```
   Open `http://127.0.0.1:8000`.
6. Paste your own LinkedIn and public Instagram links. Confirm ownership or permission. Watch retrieval and analysis progress, inspect source evidence, choose two ready agents, start a date, and then view rankings.

## Prepare a real demonstration

```bash
PYTHONPATH=backend python infra/discover.py --target 25
PYTHONPATH=backend python infra/discover.py --reuse --target 25
PYTHONPATH=backend python infra/cache_portraits.py
PYTHONPATH=backend python infra/prepare_demo.py --target 25
```

Discovery queries are generated from themes, never a fixed list of people. You can change `--themes` to public professional categories or geographical search terms. LinkedIn's source location is displayed when available; nationality is never inferred from names. The free LinkedIn actor limits a run to ten profiles, so batches contain at most ten.

The discovery pipeline admits public Instagram accounts only, requires matching public names and a self-published LinkedIn cross-link, and uses established public-facing accounts for the demonstration. Third-party search snippets locate URLs but do not enter analysis. The source data and database remain private local files; public site responses contain sanitized profile evidence rather than contact enrichment.

Re-running the same extraction reuses its existing Apify run. A uncertain provider-start outcome requires review instead of silently starting another paid run. Budget reservations remain in force until an actor finishes. No paid-plan upgrade is performed.

## What the model does

The server extracts numbered excerpts from the two retrieved snapshots. The local Qwen model selects traits and evidence IDs. The server copies the actual quote and source, validates both-source coverage, and rejects unsupported evidence references or restricted personal inferences. Unknown romantic needs remain unknown.

Each date contains four separate alternating model invocations. An agent sees its own supported traits, the existing transcript and the fictional setting. Every turn has evidence IDs. Its final turn includes its own fit estimate, reflection and remaining curiosity. Failed dates resume at the first missing turn.

Rankings exclude the current person and cover every other ready profile. Undated pairs show a lexical public-theme comparison. Dated pairs combine that comparison (40%) with the agent's average assessment across completed settings (60%). These heuristic scores are not calibrated probabilities of romantic success. The Chemistry Lab reports both directions, their gap and the lower assessment as mutual conversational fit.

The initial date round provides every ready agent with conversations. It does not imply every possible pair has dated; the interface labels this distinction. For exhaustive coverage, an operator may use `python -m pairlit.cli dates --all-pairs` while the API is stopped. At 25 people, exhaustive coverage means 300 dates and 1,200 model invocations.

## Tests

```bash
python -m pytest -q
cd apps/web
npm run typecheck
npm run build
```

Tests cover strict profile URL validation, private account rejection, source identity, quote grounding, the real API contract with isolated test doubles, four independent agent turns, deduplication, resume behavior, budget enforcement, directional rankings and scenario comparison. Fictional test fixtures never populate the live database. Browser verification uses the actual local application; scraping and model checks are separately performed against live services.

## Stack

Next.js 16 / React 19 / TypeScript frontend; FastAPI / Pydantic / SQLite backend; Ollama with Qwen3.5 4B. Apify actors: `apify/google-search-scraper` for discovery, `harvestapi/linkedin-profile-scraper` in no-email mode, and `apify/instagram-profile-scraper` for public Instagram. Public portraits are cached from those sources' CDN URLs.

`archive/coordination` holds the retired Kindweft implementation and private data. It is excluded from builds and publication. Gmail, Calendar, Telegram and Composio are not dependencies of Pairlit.

## Submission

See `docs/SUBMISSION.md` for the 200-character explanation, technical section, video outline and publication checklist. Public links and release evidence must be verified before submission. A temporary tunnel is a test/demo URL, not durable production hosting.
