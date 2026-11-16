# Independent demo catalogue: implementation notes

This branch introduces the metadata and synthetic profile fixture for Brickwise's independent demo catalogue.

## Data provenance

The 12 products are fictional. Their names, descriptions, identifiers, years and part counts are synthetic. The accompanying artwork was generated specifically for this demo and is not Rebrickable or LEGO product photography.

## Files

- `data/demo/products.csv`: 12 fictional catalogue records.
- `data/demo/synthetic_preferences.csv`: illustrative labels for one synthetic profile.
- `data/demo/demo_profile.json`: explicit profile provenance and warning.

## Isolation contract

The demo must run with its own data directory and SQLite database. It must not read, write, migrate, reset or reuse the personal `data/brickwise.db`, original catalogue images, embeddings or feedback. The preferred runtime is a separate backend process with `BRICKWISE_DATA_DIR=data/demo/runtime` and a separate port.

## Recommendation requirements

Use the existing CLIP embedding implementation and recommender service against the demo images only. Embedding IDs must match the fictional product IDs. Keep the existing minimum of three likes and three passes. The included synthetic profile has seven likes and five passes, but must be explicitly labelled synthetic in every UI surface and report.

A fresh profile must start with no feedback. Resetting the demo may only clear the demo database.

## Not yet complete

This branch currently contains metadata and synthetic preference fixtures only. Image binaries, runnable demo ingestion, embedding generation, a separate API process, frontend demo routes, and automated isolation tests are not yet included. Do not treat this branch as a working demo until those pieces are implemented and verified.
