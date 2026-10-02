# Recovr User Guide

Recovr is a lost-and-found platform for campuses. Students report lost items, staff log found items, Recovr
suggests likely matches from photos, and staff verify ownership before anything is returned.
**Report it. Match it. Verify it. Recover it.**

## 1. Start the app (Windows PowerShell)
    cd path\to\Recovr-main
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python seed_demo.py        # optional: loads a labelled DEMO institution (prints its join code)
    uvicorn app.main:app --reload
Open http://127.0.0.1:8000. Stop with Ctrl+C. To reset: stop, delete `data\lost_found.db`, run the seed again.

## 2. Where everything is
| Page | Address | Who |
|---|---|---|
| Landing page | `/` | Everyone |
| Portal (report, claim, notifications) | `/portal` | Students, staff, admins |
| Staff console (claims, analytics) | `/staff` | Staff, admins |
| Admin portal (members, items, settings, audit) | `/admin` | Admins |
| Live test checklist | `/guide` | Everyone |
| Original UI | `/app` | Everyone |

## 3. Roles
- **User (student/visitor):** report lost items, browse found items, claim, read notifications.
- **Staff:** everything above plus report found items, review and approve/reject claims, see the dashboard.
- **Admin:** everything staff can do plus manage members and roles, edit zones, see the join code, delete items, read the audit log.
Every institution is separate: people see only the institution they belong to. (There is no platform-wide Super Admin yet.)

## 4. Create an account
1. Open `/portal`, choose **Switch log in / sign up**, enter name, email, password (8+ characters).
2. If the email already has an account you will see **"An account with this email already exists"** with a **Log in instead** link.
3. New accounts belong to no institution yet. Either **Join** with a code from your admin, or **Create an institution** (you become its admin and get a join code).
Account data (name, email, hashed password) and each person's role per institution are stored in the database file `data\lost_found.db`.

## 5. Test the whole product (also available as a tick-list at `/guide`)
1. **Sign up** a new email; sign up again with the same email to see the duplicate message.
2. **Create an institution** with zones like `library,cafeteria`; note the join code (Admin → Settings).
3. In a private window **sign up a second account** and join with the code (this is your student).
4. **Admin → Members:** add a third signed-up account as staff, or change roles from the dropdown.
5. **Student:** Report an item → Lost item, add a photo, submit.
6. **Staff/admin:** Report an item → Found item, add a similar photo, a private detail (e.g. "sticker on the bottom") and a storage location.
7. **Student:** a match appears with a Match Score and the reasons; a notification arrives.
8. **Student:** under Found items press **This is mine** and describe the private detail.
9. **Staff** (`/staff`): compare the private detail with the answer and press **Approve**, **Need more info** or **Reject**.
10. **Student:** My claims shows the status; after approval the pickup location appears.
11. **Admin:** Overview shows return rate and recovery time; Audit log lists every step.
12. **Errors:** wrong password, joining with a bad code, opening `/nothing-here`: each shows a clear message.

## 6. Finding things
- **A found item:** Portal → Found items; type in the search box to filter by name, zone or status.
- **Any item (staff/admin):** `/admin` → Items, with a live filter, or `/staff`.
- **A person's role:** `/admin` → Members. **What happened and who did it:** `/admin` → Audit log.

## 7. Demo accounts (development only; password `demo-pass-123`)
admin@demo.test, staff@demo.test, student@demo.test, student2@demo.test. Run `python seed_demo.py` first.

## 8. Troubleshooting
- *Page says "Admin access required":* log in at `/portal` with an admin account.
- *"Cannot reach the server":* make sure `uvicorn` is still running.
- *Port in use:* add `--port 8001` to the uvicorn command.
- *Match score seems low:* use clear photos on plain backgrounds; run `python evaluate_matching.py` on your own photos.
- Match Score is a heuristic similarity, not a probability. Staff make the final decision.
