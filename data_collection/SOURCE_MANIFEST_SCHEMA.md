# Source Manifest Schema

Every document entered into `data_collection/<domain>/collected/` must have a
matching JSON manifest entry with this shape (see spec section 9):

```json
{
  "source_name": "India Code",
  "source_url": "https://www.indiacode.nic.in/",
  "document_name": "Information Technology Act, 2000",
  "domain": "cyber",
  "document_type": "act",
  "jurisdiction": "India",
  "verified": true,
  "verified_date": "2026-08-30",
  "notes": ""
}
```

Field rules:

- `source_url` must be a real, checkable URL — verified by an actual web
  search/fetch during collection, not typed from memory. If a source has not
  been independently verified yet, `verified` must be `false` and the source
  must NOT be used to populate `data/raw/` until it is verified.
- `document_type` is one of: `act`, `rules`, `regulation`, `case`,
  `constitution`, `amendment`.
- `jurisdiction` is `"India"` for Central legislation, or `"India - <State>"`
  for state-specific legislation (e.g. `"India - Karnataka"`).
- Never fabricate a `source_url`. If unsure, leave the field blank and mark
  `verified: false` rather than guessing.

This manifest is consumed by `scripts/collection/collect_<domain>.py` in
Phase 3, which cross-checks every manifest entry against `verified: true`
before copying anything into `data/raw/<domain>/`.
