# Querivue

Querivue is an AI engineering portfolio project for asking questions about uploaded datasets. The planned agent routes questions to SQL or Python, reuses verified results for follow-ups, and asks for clarification when an assumption could change the answer. Results will link to inspectable evidence.

The repository currently contains the React and Django starter apps and an importable Python agent package. See the [PRD](docs/PRD.md) for the agreed scope, the [decision log](docs/memory.md) for design decisions, the [overall architecture](docs/architecture/overall.md) for system boundaries and focused component documents, and the [working rules](docs/rules.md) for our collaboration process and [coding rules](docs/coding-rules.md) for coding tasks.

## Repository layout

| Directory | Purpose |
| --- | --- |
| [`agent/`](agent/) | Standalone Python package for the agent, future CLI, and evaluations. |
| [`backend/`](backend/) | Django application and future background workers. |
| [`frontend/`](frontend/) | React and TypeScript app built with Vite. |
| [`docs/`](docs/) | PRD, decision log, and future design documents. |

## Local setup

Install Node.js with npm, Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker Desktop. The scaffold was verified with Node.js 22.18 and Python 3.12.

Copy the shared environment template from the repository root, then replace the example password with a local-only value. Do not commit `.env`.

```sh
cp .env.example .env
docker compose up -d postgres
```

Run the frontend from the repository root in one terminal.

```sh
cd frontend
npm ci
npm run dev
```

Run the Django backend from the repository root in another terminal. Django owns the Postgres schema through its migrations.

```sh
cd backend
uv sync --locked
uv run --locked --env-file ../.env python manage.py migrate
uv run --locked --env-file ../.env python manage.py check
uv run --locked --env-file ../.env python manage.py runserver
```

The Compose service binds Postgres only to loopback on port 55432 and stores its data in the persistent `postgres_data` volume. `docker compose down` preserves that volume; do not add `--volumes` unless you intend to delete the local database.

Database connections fail after 5 seconds, wait at most 5 seconds for locks, limit statements to 30 seconds, and close transactions left idle for 30 seconds. The application does not automatically retry failed database work.

For a later hosted Postgres migration, keep the same database variables and change `POSTGRES_HOST`, `POSTGRES_PORT`, and `POSTGRES_SSLMODE` as required by the provider. Set `POSTGRES_SSLROOTCERT` when the provider supplies or requires a CA certificate. Django migrations move the application schema, not database contents, provider roles, extensions, or storage objects; those need a separate migration plan.

Set up and check the standalone agent package from the repository root.

```sh
cd agent
uv sync --locked
uv run --locked python -c "import querivue_agent"
```

The frontend and backend currently run as separate starter apps. Hosted Postgres through Supabase and the CI workflow are planned. The standalone agent package keeps its own SQLite state and does not use the Django database.

## Checks

- In `frontend/`, run `npm run lint` and `npm run build`.
- In `backend/`, run `uv run --locked --env-file ../.env python manage.py check`.
