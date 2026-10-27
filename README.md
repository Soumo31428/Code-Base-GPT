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
2. Build and start the Docker services:

```bash
docker compose up --build -d
```

3. Confirm PostgreSQL and Redis are running:

```bash
docker ps
```

4. Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```bash
.venv\Scripts\activate
```

5. Install dependencies:

```bash
pip install -r requirements.txt
```

6. Create migrations if needed:

```bash
python manage.py makemigrations
```

7. Apply migrations:

```bash
python manage.py migrate
```

8. Run Django locally:

```bash
python manage.py runserver
```

9. In another terminal, activate the same virtual environment and run Celery locally:

```bash
celery -A config worker -l info --pool=solo
```

10. The API will be available at `http://localhost:8000/api/v1/`.

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

Base session endpoints:

- `POST http://localhost:8000/api/v1/sessions/`
- `GET http://localhost:8000/api/v1/sessions/{id}/`

### Example 1: FastAPI dependency injection internals

Request:

```json
{
  "source_type": "github",
  "repo_url": "https://github.com/tiangolo/fastapi",
  "question": "How does FastAPI handle dependency injection internally?"
}
```

Observed answer:

```json
{
  "question": "How does FastAPI handle dependency injection internally?",
  "answer": "FastAPI’s dependency injection is centered around two internal steps:\n\n1. **Build a dependency graph**\n   - `get_dependant()` is the function that constructs a `Dependant` representation for a callable and its dependencies. It appears in `fastapi/dependencies/utils.py` and is used recursively, including for sub-dependencies. [fastapi/dependencies/utils.py:284-331] [fastapi/dependencies/utils.py:332-379]\n   - The code path also shows `return get_dependant(...)`, which indicates FastAPI reuses this function to build dependency metadata from one callable to the next. [fastapi/dependencies/utils.py:128-175]\n\n2. **Resolve the dependencies at request time**\n   - `solve_dependencies()` is the async function that actually resolves those dependencies. It is defined in `fastapi/dependencies/utils.py` and is also referenced from routing code. [fastapi/dependencies/utils.py:596-643] [fastapi/routing.py:49-96]\n   - The text evidence shows `solved_result = await solve_dependencies(...)`, which means FastAPI performs dependency resolution during request handling before calling the endpoint. [fastapi/dependencies/utils.py:647-694]\n\nIn short, **FastAPI first analyzes endpoint callables with `get_dependant()` to build a dependency tree, then executes that tree with `solve_dependencies()` when a request comes in**. [fastapi/dependencies/utils.py:284-"
}
```

### Example 2: AI integration discovery in a real repository

Request:

```json
{
  "source_type": "github",
  "repo_url": "https://github.com/injamul3798/ai-survey-platform",
  "question": "Tell me about ai integrations of this system ,what ai service they use."
}
```

Observed answer:

```json
{
  "question": "Tell me about ai integrations of this system ,what ai service they use.",
  "answer": "From the supplied findings, this system does have an AI-related component for survey generation: `backend/app/services/survey_ai.py` imports prompt definitions from `backend/app/prompts/survey_generation.py`, and the prompt file uses survey generation request schemas such as `SurveyGenerateRequest` and `QuestionRegenerateRequest` [backend/app/services/survey_ai.py:8-28] [backend/app/prompts/survey_generation.py:3-23].\n\nWhat AI service they use is **not shown in the findings**. There is no explicit reference here to a provider/API name like OpenAI, Anthropic, Azure OpenAI, etc. So, based only on the supplied evidence, the exact AI service is **unknown**. [backend/app/services/survey_ai.py:8-28]\n\nInferred: the system likely has an AI-powered survey generation feature, but the specific model/provider cannot be determined from these snippets alone. [backend/app/services/survey_ai.py:8-28] [backend/app/prompts/survey_generation.py:3-23]"
}
```

You can still inspect individual sessions and repository history through:

```bash
curl http://localhost:8000/api/v1/sessions/1/
```

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
