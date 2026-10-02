# Recovr for Campuses — what was added (v0.2)

**Business model (Assumption, not market data):** free for individuals, paid SaaS for institutions.
Plan prices are placeholders, configurable and unvalidated: Free $0, Campus ~$99-299/mo, Enterprise custom.

## Run on Windows (PowerShell)
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt pytest ruff
    python seed_demo.py          # creates labelled DEMO institution + users
    uvicorn app.main:app --reload
Open http://127.0.0.1:8000 (student/user UI) and http://127.0.0.1:8000/staff (staff console).
Demo logins (development only), password `demo-pass-123`: admin@demo.test, staff@demo.test,
student@demo.test, student2@demo.test. Tests: `python -m pytest`.

## Workflow implemented
Report lost (member) -> report found (staff only) -> matching runs inside the same institution ->
notification -> claim with a private detail -> staff Approve / Reject / Need more info ->
item `returned` -> dashboard + audit log update. Pickup location is released only after approval.

## API (all under /api or /api/v1)
POST /orgs, GET /orgs/mine, POST /orgs/{id}/members, GET /orgs/{id}/items|claims|audit|dashboard,
POST /items (now accepts org_id, private_detail, storage_location), POST /items/{id}/claims,
GET /claims/mine, POST /claims/{id}/decision, GET /notifications, POST /notifications/{id}/read.

## Honest limitations
- Match Score is a heuristic (ORB + hash + HSV + category/zone/date), not a validated probability.
  No real-photo evaluation has been run yet. Test Result: none yet.
- No CSRF tokens (SameSite=Strict cookies only), no rate limiting, no email, no payments, no Super Admin role.
- Schema changes are applied by idempotent startup code, not a migration tool (Alembic is the next step).
- Zones are a comma-separated list on the organization, not a campus/building table.
- The original landing page and user UI are unchanged and not yet org-aware; the staff console is the new UI.
- Demo seed images are synthetic drawings, so unrelated demo items can also appear as weak matches.

## Pages and design system (v0.3)
`/` landing + pricing, `/portal` student portal (login, report lost, found items, claims, notifications),
`/staff` staff console, `/app` original UI. All share `app/static/recovr.css` (one palette, one serif/sans
pairing, one container width, one nav) so every screen reads as one product.

## Real-photo evaluation
Put photos in `eval_data/<object>/*.jpg` (2+ per object), run `python evaluate_matching.py`.
It prints top-1 / top-3 results computed from your photos. Test Result: not run yet.
