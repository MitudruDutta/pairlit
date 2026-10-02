# Pairlit submission

## Overall explanation (under 200 characters)

Pairlit turns public LinkedIn and Instagram profiles into evidence-backed agents that date, compare chemistry across settings, and rank conversational fit for each person.

## Links

- Live website and completed example: https://pairlit-social.mitudrudutta72.workers.dev
- Public code: https://github.com/MitudruDutta/pairlit
- Video: upload `docs/artifacts/pairlit-demo.mp4` to YouTube and paste the resulting URL into the submission.

The website is hosted on Cloudflare Workers with D1 storage and Workers AI (Llama 3.1 8B) generating agent turns.

## Technical section

Next.js 16, React 19 and TypeScript serve the browser experience. FastAPI, Pydantic and SQLite manage profiles, durable jobs, transcripts and rankings. Ollama runs Qwen3.5 4B locally for profile analysis and four separate alternating agent turns per date.

Apify's Google Search Scraper discovers LinkedIn URLs dynamically. Search content is not analyzed. HarvestAPI's LinkedIn Profile Scraper reads public LinkedIn profiles in no-email mode, in batches of at most ten. Apify's Instagram Profile Scraper reads the associated public accounts and rejects private or unknown-visibility profiles. Source identity is checked using self-published cross-links and matching public names. Every profile uses exactly those two sources. Public portraits are cached from their source CDN URLs.

Analysis traits reference real excerpts copied by the server. Agents cite their own profile traits, react to earlier turns and assess conversational fit independently. Immutable analysis snapshots preserve the evidence used by each date. Rankings cover every other ready agent and distinguish completed conversations from undated profile comparisons. The Chemistry Lab compares both agents' assessments across different settings.

## Video order, maximum three minutes

1. Show the real workspace and public profiles, including India-based people.
2. Paste the two official links and inspect the analysis before any ranking.
3. Show the model reading source evidence, interests, hobbies, expressed priorities and unknowns.
4. Start an actual agent date. Show alternating turns, their source evidence and reflections.
5. Compare settings in the Chemistry Lab, then show an individual's rankings and open the underlying conversation.

All dates are fictional public-profile simulations. No real-world participation, romantic availability or sexuality is inferred. The example contains real extracted source data, not seeded candidates. One sourced profile may need attention if the model cannot meet evidence requirements; failed work is displayed explicitly rather than replaced with fabricated traits.
