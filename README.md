# Querivue

Querivue is an AI engineering portfolio project for asking questions about uploaded datasets. The planned agent routes questions to SQL or Python, reuses verified results for follow-ups, and asks for clarification when an assumption could change the answer. Results will link to inspectable evidence.

The repository currently contains the React and Django starter apps and an importable Python agent package. See the [PRD](docs/PRD.md) for the agreed scope, the [decision log](docs/memory.md) for design decisions, the [overall architecture](docs/architecture/overall.md) for system boundaries and focused component documents, and the [working rules](docs/rules.md) for our collaboration process.

## Repository layout

| Directory | Purpose |
| --- | --- |
| [`agent/`](agent/) | Standalone Python package for the agent, future CLI, and evaluations. |
| [`backend/`](backend/) | Django application and future background workers. |
| [`frontend/`](frontend/) | React and TypeScript app built with Vite. |
| [`docs/`](docs/) | PRD, decision log, and future design documents. |

## Local setup

Install Node.js with npm, Python 3.12, and [uv](https://docs.astral.sh/uv/). The scaffold was verified with Node.js 22.18 and Python 3.12.

Run the frontend from the repository root in one terminal.

```sh
cd frontend
npm ci
npm run dev
```

Run the Django backend from the repository root in another terminal. The starter settings use local SQLite.

```sh
cd backend
uv sync --locked
uv run --locked python manage.py migrate
uv run --locked python manage.py runserver
```

Set up and check the standalone agent package from the repository root.

```sh
cd agent
uv sync --locked
uv run --locked python -c "import querivue_agent"
```

The frontend and backend currently run as separate starter apps. Integrated local runs with Docker Compose, hosted Postgres through Supabase, and the CI workflow are planned.

## Checks

- In `frontend/`, run `npm run lint` and `npm run build`.
- In `backend/`, run `uv run --locked python manage.py check`.
