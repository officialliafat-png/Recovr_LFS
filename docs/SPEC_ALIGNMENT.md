# Spec Alignment

The provided design doc is a production-grade roadmap. This repository implements a scoped, GitHub-ready MVP that is realistic for a SWE intern portfolio while preserving clear extension points for the full system.

## Implemented in This MVP

- Lost and found listing creation.
- Category, color, free-text location, campus zone, and event date fields.
- Public browse/search with `type`, `kind`, `category`, `q`, `campus_zone`, `cursor`, and `limit`.
- Spec-aligned `/api/v1/listings` endpoints plus simpler `/api/items` aliases used by the UI.
- Image upload validation through OpenCV image decoding.
- OpenCV matching with ORB features, perceptual hash similarity, and HSV color histograms.
- Combined score that adds category, campus-zone, and date bonuses to the image score.
- Email/password signup and login.
- Salted password hashing and server-side session records.
- Supabase-ready Postgres connection support through `DATABASE_URL`.
- Supabase Storage support for hosted item photos.
- Contact privacy: public listing and match responses do not reveal raw contact details.
- Owner-only listing management: view your posts, edit details/status, resolve, and delete.
- Browser UI, Docker setup, Render blueprint, GitHub Actions CI, tests, architecture notes, hosting guide, and portfolio copy.

## Deliberately Deferred

- JWT refresh, email verification, and password reset.
- Multi-photo listings.
- In-app messaging and mutual match confirmation.
- Email notifications and daily digests.
- Admin moderation dashboard.
- Leaflet map picker and radius search.
- pgvector, Redis, Celery, and background workers.
- CNN/CLIP embeddings and approximate nearest-neighbor vector search.

## Why This Scope

For recruiting, the first version should be easy for a reviewer to clone and run. A large distributed stack is impressive only if it is reliable and finished. This MVP demonstrates the core product workflow and the computer-vision differentiator, then documents how the architecture evolves into the full design.

## Recommended Next Upgrade

The strongest next step is storing image signatures in the database, then adding a `matches` table with unique `(lost_listing_id, found_listing_id)` pairs. That unlocks match history, confirmation, messaging, and race-condition tests without requiring a full cloud deployment. For auth, the next production step is email verification plus a password-reset flow.
