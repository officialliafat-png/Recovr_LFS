# Hosting Recovr

This guide deploys Recovr as one public FastAPI service with shared cloud storage.

## Recommended Hosted Architecture

- App server: Render or Railway, deployed from GitHub with the Dockerfile.
- Database: Supabase Postgres using `DATABASE_URL`.
- Uploaded images: Supabase Storage bucket named `recovr-items`.
- Local development: SQLite plus local uploads still works without cloud credentials.

This gives the portfolio project the behavior users expect: every device opens the same URL, sees the same reports, and keeps data after the app restarts.

## 1. Create Supabase Resources

1. Create a new Supabase project.
2. In Storage, create a public bucket named `recovr-items`.
3. In Project Settings, copy the Project URL.
4. In Project Settings > API, copy the service role key.
5. In Database > Connect, copy the **Shared Pooler / Session mode** Postgres connection string.

Do not use the direct database URL that starts with `db.<project-ref>.supabase.co`. Supabase direct connections use IPv6 on free projects, and Render cannot reach IPv6-only Supabase database hosts. Use the pooled IPv4 URL instead.

The recommended Supabase URL shape for Render is:

```text
postgresql://postgres.<project-ref>:<database-password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

The transaction pooler on port `6543` can also work because Recovr disables prepared statements for psycopg, but the session pooler on port `5432` is simpler for this persistent Docker web service. Do not put these secrets in Git.

## 2. Set Render Environment Variables

Create a Render Web Service from the GitHub repo and choose Docker.

Recommended Render settings:

```text
Runtime: Docker
Dockerfile Path: ./Dockerfile
Health Check Path: /api/health
```

If you create a Python runtime service instead of Docker, use:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set these environment variables in Render:

```text
DATABASE_URL=<your Supabase pooled Postgres connection string>
LOSTFOUND_COOKIE_SECURE=true
LOSTFOUND_STORAGE_BACKEND=supabase
LOSTFOUND_SUPABASE_URL=<your Supabase project URL>
LOSTFOUND_SUPABASE_SERVICE_ROLE_KEY=<your Supabase service role key>
LOSTFOUND_SUPABASE_STORAGE_BUCKET=recovr-items
LOSTFOUND_SESSION_DAYS=7
LOSTFOUND_MATCH_THRESHOLD=0.42
```

Render supplies `PORT` automatically. The Dockerfile starts Uvicorn on that port.

## 3. Deploy

1. Push the latest code to GitHub.
2. In Render, create or refresh the web service deployment.
3. Open `/api/health` on the Render URL and confirm it returns `{"status":"ok"}`.
4. Open the main URL, create an account, post an item with a photo, then refresh the page.

## 4. Security Notes

- Keep `LOSTFOUND_SUPABASE_SERVICE_ROLE_KEY` server-side only.
- Use `LOSTFOUND_COOKIE_SECURE=true` on HTTPS deployments.
- Do not commit `.env`, database files, uploaded photos, or service keys.
- Supabase Storage is public in this MVP so listing images can render directly in the browser.
- A production campus launch should add email verification, password reset, CSRF protection, private image delivery, admin moderation, and abuse controls.

## 5. Local Development Still Works

Leave `DATABASE_URL` empty and keep:

```text
LOSTFOUND_STORAGE_BACKEND=local
LOSTFOUND_DB_PATH=data/lost_found.db
LOSTFOUND_UPLOAD_DIR=data/uploads
LOSTFOUND_COOKIE_SECURE=false
```

Then run:

```bash
uvicorn app.main:app --reload
```
