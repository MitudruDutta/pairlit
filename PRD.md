# Pairlit — agentic dating

## Goal
Build the supplied agentic dating task: at least 25 real adults, each with their own public LinkedIn and public Instagram. Exactly those two accounts supply all profile information. Each person has an agent, an inspectable analysis page, agent-to-agent dates, and a personalized ranking.

## Required journey
1. Paste a LinkedIn profile URL and public Instagram profile URL.
2. Fetch both sources. Show progress, source timestamps, source identity, and explicit failures. Private Instagram accounts and mismatched identities cannot qualify.
3. Analyze only the two source snapshots. Present interests, hobbies, expressed priorities, supported qualities, evidence excerpts, and unknowns. Never invent relationship status, sexual orientation, private needs or availability.
4. Create a distinct agent with its own source-grounded interests and questions. Two agents take alternating turns through a first-date scenario. Each observes the existing conversation and chooses a response; save the full transcript and individual reflections.
5. Rank all other ready profiles for each person. Show directional fit, shared topics, potential friction, missing information, and which dates support the result. Distinguish an initial profile comparison from a completed date.
6. Provide a pre-run demo with at least 25 successfully sourced, analyzed real people and date coverage for every agent.

## Presentation
Profiles appear before rankings. A live date view visibly shows the two agents conversing and reacting. The website accepts fresh public links and runs the same ingestion and analysis pipeline used for the demo. Agent conversations are explicitly simulations; the depicted people are not claimed to have joined or authorized real-world dating. No real people are messaged.

## Sources and identity
Discovery can locate candidate URLs; analysis receives only retrieved LinkedIn and Instagram content. Demo candidates are public adult creators/professionals with official matching profiles. Do not retain contact-email enrichment, telephone numbers, private accounts, third-party comments or posts by other people. Record identity-review status separately from source retrieval. Names alone do not prove an official account pair.

## Acceptance
- At least 25 real, verified pairs; exactly two source snapshots per accepted profile.
- Unsupported claims remain unknown; every extracted trait has a valid source quote.
- Agents have separate turns, source-grounded behavior, visible transcripts and directional assessments.
- Each profile ranks every other ready profile; no self-rank and no unrun date labeled completed.
- Durable jobs and results survive restart. Failed scraping or model output is visible and retryable.
- Unit/integration tests cover source URL restrictions, privacy, evidence grounding, ranking and real API flows; browser tests exercise ingestion through rankings.
- A video of at most three minutes shows 25 people, profile analysis first, live agent dates, and rankings.

## Submission
YouTube video, pre-run demo link, working public site, public GitHub repository, a 200-character explanation, and scraper/stack explanation. Missing external publication is reported as missing, never fabricated.

## Scope removed
Gmail, Calendar, Telegram, commitment renegotiation, helper coordination, calendar write approvals, recovery episodes and their release gates are retired. Prior code/data are stored privately in archive/coordination and excluded from the new submission.
