# Sc2ReplayStats integration

The project has an optional, read-only Sc2ReplayStats integration for supplemental account data. It is deliberately not a second replay parser.

## Authentication

The documented API requires the exact value from the account's API Access page in the `Authorization` header. The value has three semicolon-separated fields (`hash;token;timestamp`); it is not a Bearer token. Configure only the environment-variable name in `config.toml`:

```toml
[sc2replaystats]
enabled = true
base_url = "https://api.sc2replaystats.com"
auth_env = "SC2REPLAYSTATS_AUTH"
cache_ttl_seconds = 900
```

Then export the secret locally:

```bash
export SC2REPLAYSTATS_AUTH='hash;token;timestamp'
```

The secret is never written to the repository, config, output, cache metadata, exception text, or `run-metadata.json`. `.env` files are ignored, but environment variables are preferred.

## Pull behavior

`analyze` calls `GET /account/last-replay` and, when an ID is present, requests replay detail from `GET /replay/{replay_id}` with the documented `players`, `account`, `players-replay-info`, and `map` includes. No upload endpoint is called.

The result is cached by the local replay content hash under `.cache/sc2replaystats/<replay-hash>/sc2replaystats.json`. The default TTL is 15 minutes. `--refresh-sc2replaystats` bypasses the cache for one analysis.

The external payload is compared to the local replay using a high-confidence hash match when available, then a lower-confidence map/participant-name comparison. An unverified remote result is preserved but is not silently treated as the same replay.

## Data boundaries

Local s2protocol facts remain the canonical extraction. Sc2ReplayStats data is stored as supplemental external data in `sc2replaystats.json` and summarized in the evidence layer. It is not merged into `findings.json`, and no external metric is promoted into `review.md` until its response field semantics are verified and versioned.

Missing credentials, HTTP errors, timeouts, invalid JSON, and unmatched remote replays are non-fatal. The local replay report still completes with an explicit external status.

## API reference

The endpoint and header behavior are based on the [Sc2ReplayStats API documentation](https://api.sc2replaystats.com/docs/index.html).
