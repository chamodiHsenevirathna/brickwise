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

## Running it

```bash
cd backend && ../.venv/bin/python -m brickwise.data.demo_artwork   # optional: regenerate the 12 original images
../.venv/bin/python -m brickwise.data.demo_ingest                  # demo DB + CLIP embeddings in data/demo/runtime/
../.venv/bin/uvicorn brickwise.api.demo:create_default_app --factory --port 8001
cd ../frontend && npm run dev:demo                                 # http://localhost:5174
```

The example profile seeds 10 of the 12 synthetic ratings (holding out `BW-009` and `BW-011`) so that recommendations have candidates and the evaluation minimums are met. Evaluation on 12 products is illustrative only. See the README for details.
