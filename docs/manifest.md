# Catalogue format 1.0

The authoritative schema is
[`catalogue.schema.json`](../src/nvfr/data/catalogue.schema.json), JSON Schema
Draft 2020-12. All objects reject extra properties. `schema_version` must be
`"1.0"`; the application fails clearly on unsupported formats. Dates use ISO
`YYYY-MM-DD`. IDs are stable lowercase strings, not titles or version numbers.

Top-level fields: `schema_version`, `catalogue_id`, `title`, `updated_at`, `packages`.
Package IDs must be unique across all loaded catalogues. One provider listing may
correspond to several independently installed MSFS package folders.

| Package field | Meaning |
| --- | --- |
| `id` | Permanent manager ID; shipped entries use `flightsim-to-<numeric-id>` |
| `name`, `developer` | Original display title and creator username |
| `description`, `category` | Short description; category is airport, landmarks, landscape, heliport, library, other or unknown |
| `flightsim_to` | Numeric listing ID (or unknown) and original HTTPS `/addon/` or `/file/` page URL |
| `version` | Version stated by the source; `unknown` when not verified |
| `last_verified` | Date the recorded facts were checked, or `unknown` |
| `compatibility` | Separate MSFS 2020/2024 values: confirmed, reported, incompatible, unknown |
| `geography` | Country, area label, and coordinates `{latitude, longitude}` or `unknown` |
| `dependencies`, `conflicts` | Arrays of catalogue package IDs, or `unknown` |
| `license` | Name, HTTPS licence URL and redistribution permission; each can be unknown |
| `attribution` | Creator and original source credit shown in the GUI |
| `installation` | Verified MSFS `folder_names` array or unknown; human-readable notes |
| `sha256` | Lowercase 64-character hash of the **entire ZIP archive**, or unknown |
| `verification` | Status (verified/partial/unverified) and per-source date, URL, supported fields and note |

**Unknown is meaningful.** An empty dependency/conflict array states that none
are known after verification; it must not replace missing research. `reported`
means the source lists simulator support, while `confirmed` needs a documented
independent test. A version and simulator label never establish licensing rights.
The schema permits complete unknown metadata while retaining a real original URL.

`sha256` identifies one exact distributed archive. Different variants require
separate records or an unknown checksum until the data model is extended. It is
not a hash of one package folder. The engine refuses a known checksum mismatch.

The local SQLite database is separate. It stores actual package-folder identities,
archive versions, SHA-256, catalogue associations, creator/source, absolute paths,
activation method/status, ownership markers and per-file hashes. Updating a
catalogue neither edits an installed version nor moves installed files.

The [example manifest](example-manifest.json) is derived from one real listing and
illustrates conservative unknowns. It is a separate example catalogue and is not
loaded automatically alongside the bundled catalogue containing the same package.
