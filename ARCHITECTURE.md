# Pairlit architecture

Next.js static export → FastAPI → SQLite WAL. A bounded background job executor runs Apify acquisition and local Ollama inference. No hosted model dependency is required.

## Data
`profiles` stores two canonical source URLs, acquisition status, sanitized source snapshots, evidence-grounded analysis and timestamps. `dates` stores two profile IDs, scenario, alternating agent turns, individual reflections and status. `jobs` persists work, progress and errors; interrupted work is marked retryable on startup. The pre-run demo uses the same records as new submissions.

## Acquisition
Server-side Apify actors read public LinkedIn profile fields and public Instagram bios/captions. Actor runs have a per-run charge ceiling, timeout and cumulative local budget. Existing included credit is verified before use. Tokens never reach the browser. Two URLs are validated before any acquisition; there is no arbitrary-URL fetch path. Only allowlisted profile text fields enter the model. Raw provider contact enrichment is discarded.

## Agent harness
A profile analyzer produces traits with source references and verbatim support. Validation drops unsupported traits. Each date contains independent model calls, one per agent turn, using that agent's evidence and prior conversation. The agent asks a question, responds to the other agent, explores a concrete shared activity, and reflects on compatibility. Persona prompts treat scraped text as untrusted data. Public-figure simulations do not claim human participation or private romantic preferences.

## Ranking
All ready candidates receive an explainable baseline comparison using grounded interests and expressed priorities. Completed dates add reciprocal conversational evidence and individual agent reflections. Ranking exposes the basis, uncertainty and completed-date status. The score measures this simulation's compatibility, not a person's worth or willingness to date.

## Delivery
A single Python service serves API and built UI, with SQLite on a persistent volume and access to Ollama. Public evaluation uses the same live backend. Source snapshots and transcripts remain durable. Tests use controlled providers; actual demo records require real retrieved sources. No fixture dataset is presented as real.
