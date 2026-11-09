# Neon CLI output (`.env` / `.env.local`)

The app reads the files the Neon CLI writes, so a locally linked Neon branch
works without copying values by hand.

## How to produce the files

From the project root (the directory that contains `app/` and `render.yaml`):

```bash
npm i -g neon@latest
neon login                      # browser sign-in
neon init -y --org-id <org> --project-id <project> --branch production \
  --services postgres,auth,object-storage,realtime
neon deploy                     # writes .env.local
```

`neon deploy` applies the branch policy and writes the connection details to
`.env.local` (or updates an existing env file).

## What the app does with them

`app/neon_env.py` runs at config import and in the Render launcher:

| Neon key | Used as |
|---|---|
| `DATABASE_URL_UNPOOLED` | **`TT_DATABASE_URL`** (preferred) |
| `DATABASE_URL` | `TT_DATABASE_URL` fallback only |
| `NEON_AUTH_BASE_URL`, `NEON_AUTH_JWKS_URL` | left in the environment (not consumed yet) |
| `NEON_DATA_API_URL` | left in the environment (not consumed yet) |
| `NEON_REALTIME_URL`, `NEON_REALTIME_SECRET` | left in the environment (not consumed yet) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION` | left in the environment (not consumed yet) |
| `NEON_BRANCH`, `NEON_BRANCH_ID` | left in the environment |

### Why the unpooled URL

asyncpg uses prepared statements. Neon's pooled endpoint runs pgbouncer in
transaction mode, which breaks them, and it requires `options=endpoint…` —
not a valid `asyncpg.connect()` argument. The loader therefore prefers
`DATABASE_URL_UNPOOLED` and **fails closed** if only a pooled URL is available.

The mapped URL is normalized: `postgres://` → `postgresql+asyncpg://`,
`sslmode` → `ssl`, and `channel_binding` is dropped.

### Precedence

```
real environment  >  TT_NEON_ENV_FILE  >  .env.local  >  .env  >  config/secrets.env
```

Nothing already set in the environment is overwritten, so Render dashboard
values and systemd/VPS env files always win.

### secrecy

* `.env` and `.env.*` are git-ignored (only `.env.example` is tracked).
* The loader returns **key names only** — values are never logged or printed.
* `tools/check_served_secrets.py` scans web-served files for secret values.

## Render

On Render you do **not** need these files. Set `TT_DATABASE_URL` in the
dashboard to the Neon **direct** connection string; the launcher normalizes it.
`.env.local` is only for local development.

## Verify

```bash
python tools/check_neon_env.py     # 24 checks, synthetic values only
```

It is part of `verify.sh`.

## Not wired yet

Neon Auth, Object Storage, and Realtime credentials are loaded into the
environment but the app still uses its own session auth, local upload storage,
and SSE. Switching those subsystems to Neon is a separate change.
