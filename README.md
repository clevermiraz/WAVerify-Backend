# WAVerify — Backend

WAVerify tells you if a phone number has a WhatsApp account.

This is the backend. It is built with **FastAPI**, **PostgreSQL** and **Redis**.

In production it runs at **https://api.waverify.app**. The website that uses it
lives at **https://waverify.app** (see the `WAVerify-Frontend` repository).

---

## What you need first

Install these on your computer:

- [Python 3.12 or newer](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/) and
  [Docker Compose](https://docs.docker.com/compose/install/)

---

## Quick start with Docker

This is the easiest way. Docker starts the API, the database and the cache
together.

**Step 1 — copy the settings file:**

```bash
cp .env.example .env
```

**Step 2 — create a secret key.** Run this command:

```bash
openssl rand -hex 32
```

Copy the long text it prints. Open `.env` and paste it as the value of
`SECRET_KEY`. The app will not start without it.

**Step 3 — start everything:**

```bash
docker compose up --build
```

That is all. The API now runs at `http://localhost:8000`.

Open `http://localhost:8000/docs` in your browser to read the API reference and
try requests.

> **Note:** `/docs`, `/redoc` and `/openapi.json` work only when `ENVIRONMENT`
> is *not* `production`. They describe every route, including the admin API, so
> they are switched off on the live server. The customer-facing reference is the
> `/docs` page on the website instead.

---

## Running without Docker

Use this if you want to change the code and see the result immediately.

**Step 1 — start only the database and cache:**

```bash
docker compose up postgres redis -d
```

**Step 2 — make a virtual environment:**

```bash
python -m venv venv
source venv/bin/activate
```

On Windows, use `venv\Scripts\activate` instead.

**Step 3 — install the packages:**

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**Step 4 — set up the database tables:**

```bash
alembic upgrade head
```

Run this again any time you pull new code that changes the database.

**Step 5 — start the server:**

```bash
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. It restarts by itself when you save a
file.

---

## Creating an Admin User

To access the admin dashboard, you need to create an administrator account. You can generate one from the command line using this script:

```bash
PYTHONPATH=. venv/bin/python scripts/create_admin.py your-email@example.com your_secure_password
```

This will initialize the admin user and their wallet. You can then log into the frontend using these credentials.

---

## Turning on "Sign in with Google"

This is optional. If you skip it, people can still sign up with an email
address and a password.

**Step 1 —** go to the
[Google Cloud Console](https://console.cloud.google.com/apis/credentials) and
create an **OAuth client ID**. Choose **Web application** as the type.

**Step 2 —** under *Authorised JavaScript origins*, add the addresses of your
website:

```
http://localhost:3000
https://waverify.app
```

**Step 3 —** copy the **Client ID**. Put it in your `.env`:

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

**Step 4 —** put the *same* value in the frontend, as
`NEXT_PUBLIC_GOOGLE_CLIENT_ID`. The two must match, because the backend checks
that Google made the token for this exact application.

You do **not** need the client secret. The frontend gets a signed ID token from
Google, and the backend checks that signature. No secret is involved.

If `GOOGLE_CLIENT_ID` is empty, `POST /api/v1/auth/google` replies that Google
sign-in is turned off.

### How it works

1. The person clicks "Continue with Google" on the website.
2. Google gives the website a signed ID token.
3. The website sends that token to `POST /api/v1/auth/google`.
4. The backend checks the signature, checks the token was made for this app,
   and checks that Google says the email address is verified.
5. The backend finds or creates the user, then returns our own access token and
   refresh token — the same ones a normal login returns.

An account created this way has no password. That user can still set one later
using the "forgot password" link.

---

## Running the tests

The tests need a real PostgreSQL and a real Redis. They do not call WhatsApp —
that part is replaced with a fake during tests, so nothing is sent to real
phone numbers.

**Step 1 — make sure the database and cache are running:**

```bash
docker compose up postgres redis -d
```

**Step 2 — create a separate database for tests.** This keeps your normal data
safe:

```bash
docker compose exec postgres psql -U waverify -c 'CREATE DATABASE waverify_test;'
```

**Step 3 — run the tests:**

```bash
pytest tests/
```

If your `.env` uses different ports (for example 5433 for Postgres and 6380 for
Redis), tell the tests where to look:

```bash
TEST_DATABASE_URL="postgresql+psycopg://waverify:waverify@localhost:5433/waverify_test" \
TEST_REDIS_URL="redis://localhost:6380/15" \
pytest tests/
```

---

## Settings to change before going live

Open `.env` and check these:

| Setting | Why it matters |
| --- | --- |
| `ENVIRONMENT` | Set to `production`. This switches new API keys from `wav_test_` to `wav_live_`, and turns off `/docs`, `/redoc` and `/openapi.json`. |
| `SECRET_KEY` | Must be long and random. Anyone who knows it can create valid login tokens. |
| `REQUIRE_EMAIL_VERIFICATION` | Set to `true`, so unconfirmed sign-ups cannot use your quota. |
| `CORS_ORIGINS` | List only your own website addresses, separated by commas. |
| `RESEND_API_KEY` | Set your Resend API key for transactional emails, otherwise emails will just log to the console. |

---

## Where things are

| Folder | What is inside |
| --- | --- |
| `app/api/` | The URLs people call. |
| `app/services/` | The business rules. |
| `app/repositories/` | Database reads and writes. |
| `app/models/` | The database tables. |
| `app/schemas/` | The shape of each request and reply. |
| `alembic/` | Database change scripts. |
| `tests/` | The tests. |
| `scripts/` | Small helper scripts. |
