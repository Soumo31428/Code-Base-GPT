# Codebase Research Agent

Production-minded Django monolith for answering technical questions about code repositories with grounded evidence. It supports public GitHub repositories and safe local repository paths, normalizes both into a local workspace, explores the codebase with explicit tools, persists findings in PostgreSQL, and runs long research sessions in Celery.

## Architecture

- Django + DRF provide a simple API and admin surface without spreading logic across services.
- PostgreSQL stores repository metadata, persistent findings, tool logs, sessions, and reusable summaries.
- Redis backs Celery for asynchronous repository preparation and research execution.
- `ripgrep` is the primary retrieval engine because codebases respond best to exact lexical lookup.
- The agent loop stays explicit in `agent/orchestrator.py` instead of hiding flow inside a graph runtime.

## Why Lexical-First Retrieval

Lexical retrieval is the default because source code is rich in exact identifiers, filenames, imports, decorators, and string literals. That makes `rg` a better first step than embeddings for most technical questions. Semantic retrieval is intentionally left as an extension seam rather than a default dependency, which keeps v1 cheaper, simpler, and easier to reason about.

## Persistent Memory

The database is more than a job store:

- `Finding` records durable evidence with file paths and line ranges.
- `SummaryCache` stores reusable repo, directory, and file summaries.
- `ToolCallLog` makes every tool interaction traceable for debugging and tuning.
- `ResearchSession` captures answer lifecycle, cost, runtime, and iteration depth.

## Bounded Exploration

The agent avoids wandering by combining:

- hard iteration caps
- hard tool-call caps
- duplicate tool-call detection
- 150-line read clamps
- confidence-based early stopping
- one verifier-driven retry at most

## Project Layout

```text
codebase_agent/
|-- config/
|-- apps/
|   |-- repos/
|   |-- research/
|   `-- api/
|-- agent/
|   |-- orchestrator.py
|   |-- tools/
|   |-- prompts/
|   |-- retrieval/
|   |-- synthesis/
|   `-- verification/
|-- tasks/
|-- tests/
|-- fixtures/
`-- README.md
```

## Local Setup

1. Copy `.env.example` to `.env`.
2. Start PostgreSQL and Redis only:

```bash
docker compose up -d db redis
```

3. Create migrations if needed:

```bash
python manage.py makemigrations
```

4. Apply migrations:

```bash
python manage.py migrate
```

5. Run Django locally:

```bash
python manage.py runserver
```

6. In another terminal, run Celery locally:

```bash
celery -A config worker -l info
```

7. The API will be available at `http://localhost:8000/api/v1/`.

## Environment Variables

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `REPO_CACHE_ROOT`
- `SAFE_LOCAL_REPO_ROOTS`
- `AGENT_MAX_ITERATIONS`
- `AGENT_MAX_TOOL_CALLS`
- `AGENT_TOOL_TIMEOUT_SECONDS`
- `AGENT_SEARCH_MAX_RESULTS`
- `AGENT_READ_MAX_LINES`

## API Examples

Create a GitHub-backed session:

```bash
curl -X POST http://localhost:8000/api/v1/sessions/ \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "github",
    "repo_url": "https://github.com/owner/repo",
    "question": "How does retry work?"
  }'
```

Create a local-path session:

```bash
curl -X POST http://localhost:8000/api/v1/sessions/ \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "local",
    "local_path": "/workspace/project",
    "question": "How does retry work?"
  }'
```

Fetch a session:

```bash
curl http://localhost:8000/api/v1/sessions/1/
```

List repository sessions:

```bash
curl http://localhost:8000/api/v1/repos/1/sessions/
```

## Operational Tradeoffs

- The system stays monolithic to keep debugging, deployment, and ownership simple.
- GitHub cloning is public-only in v1 to avoid auth sprawl.
- Semantic retrieval is deferred by default so cost and operational load stay predictable.
- `/stream/` is intentionally deferred; polling session status keeps the first version simpler to operate.
- Test settings fall back to SQLite automatically so local test runs do not require a live PostgreSQL service, while production remains PostgreSQL-backed.
- Docker is used only for infrastructure services in local development; Django and Celery run directly on the host machine.
