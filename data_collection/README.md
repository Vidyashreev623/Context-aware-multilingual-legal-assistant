# Data Collection

This folder is strictly about *sourcing* raw legal material — it does not
contain processing/chunking logic (that lives in `scripts/` and writes to
`data/processed/`, see the project root README).

## Structure

Each legal domain (`consumer/`, `contract/`, `cyber/`, ...) has:

- `sources.md` — a human-curated, citation-backed list of authoritative
  sources for that domain (Acts, Rules, official case-law repositories,
  government legal portals). No source is added without a verifiable URL.
- `download_scripts/` — scripts that fetch documents from those sources
  into `collected/`.
- `collected/` — raw downloaded files, later copied/moved into
  `data/raw/<domain>/` for the processing pipeline to pick up.

## Adding a new domain

1. `mkdir -p data_collection/<domain>/{download_scripts,collected}`
2. Write `data_collection/<domain>/sources.md`
3. Mirror the same domain name under `data/raw/<domain>/` and
   `data/processed/<domain>/`
4. Add `scripts/processing/process_<domain>.py`

This is done in Phase 2.

## Verified sources (this pass)

`sources.md` and `manifest.json` in every domain folder were populated
using sources found and independently checked via web search on
2026-08-30. Verified authoritative hosts used across domains:

- **India Code** (`indiacode.nic.in`) — official Government of India
  digital repository of all Central and State Acts. Used as the primary
  or backup source for nearly every domain.
- **MeitY** (`meity.gov.in`) — nodal ministry for the IT Act, 2000 (cyber).
- **RBI** (`rbi.org.in`) — central bank regulator for banking law.
- **Ministry of Corporate Affairs** (`mca.gov.in`) — nodal ministry for
  the Companies Act, 2013 (corporate).
- **Supreme Court of India** (`main.sci.gov.in/judgments`) and
  **e-Courts** (`judgments.ecourts.gov.in`) — official judgment portals.

Sources marked `"verified": false` in a domain's `manifest.json` (there
are none as of this pass, but future additions may have them) must NOT be
copied into `data/raw/` until independently re-verified — see
`SOURCE_MANIFEST_SCHEMA.md`.

## Running the collectors

```bash
python scripts/collection/collect_cyber.py
# ... one script per domain, same pattern
```

Each script validates its domain's `manifest.json` and reports whether
every source URL is reachable. It does not bulk-download documents
automatically (deliberately — official government PDFs should be fetched
and spot-checked individually, not silently scraped in bulk).

**Note on sandboxed dev environments:** some CI/sandbox environments
restrict outbound network access to an allowlist that does not include
`.gov.in` domains, which will show as `UNREACHABLE` (DNS failure) even
though the source is a real, working government site. Government portals
also commonly return `HTTP 403` to scripted requests without a browser
User-Agent/session — the collector treats 403 as "reachable, blocks
bots" rather than dead, since manual/browser access still works.
