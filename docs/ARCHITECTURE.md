# Architecture

Recovr is scoped as a recruiting-ready MVP: it solves the core lost-and-found workflow end to end, keeps deployment simple, and makes the computer-vision tradeoffs visible.

## System Shape

- `FastAPI` serves both the JSON API and a lightweight browser UI.
- `SQLite` stores item reports locally; `DATABASE_URL` switches production to Supabase Postgres.
- Local email/password auth stores salted password hashes and hashed server-side sessions.
- Uploaded images are stored on disk locally, or in Supabase Storage when `LOSTFOUND_STORAGE_BACKEND=supabase`.
- `OpenCV` computes image signatures at match time and ranks opposite-kind reports.
- Public API responses redact contact information until a future confirmation flow exists.
- Owner-only management endpoints let users list, edit, resolve, and delete their own reports.
- Tests generate synthetic images so the vision pipeline is deterministic in CI.

## Authentication

Users sign up with display name, email, and password. Recovr normalizes email addresses, stores passwords as salted PBKDF2-HMAC-SHA256 hashes, and verifies passwords with constant-time comparison. A successful signup or login creates a cryptographically random session token. The database stores only the token hash, while the browser receives the original token in an `HttpOnly`, `SameSite=Strict` cookie.

This is intentionally simple for an MVP, but it avoids the main portfolio red flags: no plaintext passwords, no readable auth token in `localStorage`, no public contact leak, and no anonymous report creation.

## Matching Pipeline

The matcher combines three signals:

1. ORB feature matching for local visual details such as logos, stickers, and edges.
2. Average perceptual hash similarity for coarse object shape and composition.
3. HSV color histogram correlation for dominant color similarity.

The final score is weighted toward ORB features, with hash and color as stabilizers. This is a strong MVP because it is explainable, fast on small datasets, and requires no model download. It is not a replacement for a trained detector; the README calls out the next step of adding embeddings or a hosted classifier when the dataset is large enough.

## API Surface

- `POST /api/v1/listings` creates a lost or found report and returns immediate matches.
- `GET /api/v1/listings` lists open reports with text and metadata filters.
- `GET /api/v1/listings/mine` lists the signed-in user's reports, including resolved posts.
- `PATCH /api/v1/listings/{item_id}` edits owner-managed listing fields and status.
- `DELETE /api/v1/listings/{item_id}` deletes an owner-managed listing.
- `GET /api/v1/listings/{item_id}/matches` ranks likely opposite-kind matches.
- `POST /api/search/image` searches with an image that is not saved as a report.
- `POST /api/v1/listings/{item_id}/resolve` marks a report as resolved.
- `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me` manage accounts and sessions.

## Data Model

Each item stores:

- report kind: `lost` or `found`
- title, description, category, color, free-text location, campus zone, and event date
- reporter user id, display name, and private contact
- image path
- status and creation timestamp

Each user stores:

- unique id, normalized email, display name, password hash, and creation timestamp

Each session stores:

- hashed session token, user id, creation timestamp, and expiration timestamp

## Scaling Path

- Store image signatures in a separate table to avoid recomputing them.
- Move uploaded images to S3 or Cloudflare R2.
- Replace pairwise matching with an approximate nearest-neighbor index such as pgvector.
- Add CLIP or MobileNet embeddings for semantic matching.
- Add email verification, password reset, CSRF protection for cross-site deployments, moderation, and in-app match confirmation before a public campus deployment.
