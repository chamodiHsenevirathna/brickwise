# Third-party notices

Brickwise's own source code and documentation are the only things the project's eventual licence will cover
(no licence has been selected yet). Everything below is owned by someone else and stays under its own terms.

## Data and images (not included in this repository)

| Item | Source | Status |
|---|---|---|
| Sets and themes CSVs | Rebrickable (https://rebrickable.com/downloads/) | Terms **not verified** by this project. Credit Rebrickable.com. Not redistributed here. |
| Set photographs | Hosted on Rebrickable's CDN; owned by their respective rights holders | Terms **not verified**. Not redistributed. Downloaded only to the user's local `data/images/`. |
| Set names / numbers shown in README screenshots | Rebrickable catalogue metadata | Open question: confirm acceptable for public display. |

Rebrickable's downloads page and terms page could not be read automatically while preparing this release
(HTTP 403), so no claim about what they permit is made here.

## Trademarks

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorise or endorse this project.
Rebrickable® is a trademark of Rebrickable. All other names belong to their owners.

## Model weights (downloaded at first run, not bundled)

| Item | Detail |
|---|---|
| Weights | `laion/CLIP-ViT-B-32-laion2B-s34B-b79K` on Hugging Face, loaded by OpenCLIP as `ViT-B-32` / `laion2b_s34b_b79k` (`open_clip_model.safetensors`) |
| Declared licence | MIT (model card metadata: `license: mit`) |
| Training data | The English 2-billion-sample subset of LAION-5B. The model card describes it as uncurated and says it may contain disturbing content. |
| Intended use (model card) | A research output for research communities. The card states that "any deployed use case of the model - whether commercial or not - is currently out of scope", that surveillance and facial-recognition uses are always out of scope, and that use should be limited to English. |
| Requested credit | Cite the OpenAI CLIP paper (Radford et al., ICML 2021) and OpenCLIP (Ilharco et al., doi 10.5281/zenodo.5143773); the card acknowledges stability.ai for training compute. |

Brickwise is a local research and portfolio demonstration. It is not a deployed product, and it uses the weights only to
embed product images for similarity. Anyone who hosts it publicly or builds a commercial service on it should re-read the
model card, because those uses are outside what the card says the model is intended for. Whether the licence of the training
images carries through to the weights is not addressed by the model card and is not resolved here.

## Libraries (used, not bundled)

Direct Python dependencies, as declared in their installed package metadata: PyTorch (Apache-2.0 and BSD terms), OpenCLIP
(MIT), FAISS (MIT), scikit-learn (BSD-3-Clause), NumPy (BSD-3-Clause and permissive components), Pillow (MIT-CMU), FastAPI
(MIT), Pydantic (MIT), Uvicorn (BSD-3-Clause), httpx (BSD-3-Clause), pytest (MIT).

Direct JavaScript dependencies: React, React DOM, react-router-dom, Vite, Tailwind CSS, PostCSS, Autoprefixer, Vitest, jsdom
and Testing Library (all MIT), TypeScript (Apache-2.0). Across the full installed JavaScript tree, every package is MIT, ISC,
Apache-2.0, BSD, MIT-0 or CC-BY-4.0 (`caniuse-lite`, browser-support data used only at build time). No copyleft licences were found.
These are not bundled with the repository; they are installed from their own sources under their own licences.
