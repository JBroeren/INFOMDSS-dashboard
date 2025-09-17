### Base hostname
- Yes. Use the regatta‑next API host (e.g. `https://api.regatta.time-team.nl`) and call paths like `/api/1/...`. Ensure your frontend origin is allowed by CORS on that host.

### Crawl order (client-side)
- Optional bootstrap (once):
  - GET `/api/1/filter_types`
  - GET `/api/1/filter`
- Discover regattas:
  - GET `/api/1/regatta` → list of regattas with IDs, codes, years
- For each regatta (use regatta_id; run these in parallel):
  - GET `/api/1/{regatta_id}`      → regatta summary + possible IDs (rankings, clubs, etc.)
  - GET `/api/1/{regatta_id}/event`→ list of events (+ event_id, round_id references)
  - GET `/api/1/{regatta_id}/race` → list of races
  - GET `/api/1/{regatta_id}/communication`
- For each event_id (parallel):
  - GET `/api/1/{regatta_id}/event/{event_id}/entry`
  - GET `/api/1/{regatta_id}/event/{event_id}/final`
  - For each round_id you encounter: GET `/api/1/{regatta_id}/event/{event_id}/round/{round_id}`
- Rankings (only if you have IDs from previous responses):
  - GET `/api/1/{regatta_id}/ranking/{regatta_ranking_id}`
  - GET `/api/1/{regatta_id}/event/{event_id}/ranking/{regatta_ranking_id}`
- Clubs and members (hydrate only when IDs appear in prior payloads):
  - GET `/api/1/{regatta_id}/club/{club_id}`
  - GET `/api/1/{regatta_id}/club_member/{club_member_id}`
- Containers/series (if needed):
  - GET `/api/1/container/{regatta_container_id|path}/regatta`
  - GET `/api/1/container/{...}/ranking`
  - GET `/api/1/container/{...}/event_container`
  - GET `/api/1/container/{...}/event_container/{event_container_id}`
  - GET `/api/1/container/{...}/event_container/{event_container_id}/ranking`
- On-demand lookups:
  - GET `/api/1/person/{person_id}`
  - GET `/api/1/search` (or `/api/1/{regatta_id}/search`) when you need to discover IDs by text

Notes:
- Do calls per regatta in parallel with throttling; respect cache headers (`public, max-age=30`).
- Prefer IDs; only fall back to `{code}/{year}` variants if ID isn’t known.