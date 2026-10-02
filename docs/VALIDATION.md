# Release verification

Verified on 2026-10-02 against the actual local application and its public tunnel.

| Check | Result |
|---|---|
| Real two-source extraction | Fresh LinkedIn and Instagram extraction completed; identity was cross-linked |
| Real people | 26 public-source records; 26 grounded analyses ready |
| India coverage | 8 profiles state an India location on LinkedIn |
| Agent date coverage | All 26 ready agents participated in a completed four-turn conversation |
| Portraits | 26 source portraits cached |
| Public API | HTTPS `/health` returned 200, product Pairlit |
| Backend contracts | URL, visibility, identity, grounding, budget, model-call, resume, ranking and chemistry tests |
| Frontend | TypeScript check and production static export |

The counts describe the verified example, not hardcoded website values. Live statistics come from SQLite. Rankings are heuristic conversational-fit estimates, not validated predictions of romantic success. Not every possible pair has dated; undated pairs are labeled.

Credentials, private provider data, SQLite files, retired coordination services and recorded artifacts are excluded from the public repository. The local video artifact must be uploaded to YouTube separately. The public tunnel remains available only while its supporting processes run.

Backend suite: 15 tests passed. Gateway contract checks passed. Frontend typecheck and production build passed. Public-browser checks passed with no JavaScript errors and no mobile horizontal overflow.
