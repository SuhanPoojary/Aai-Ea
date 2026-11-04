# AegisSupport 2.0 — Agentic Customer Support

A React + FastAPI customer-support demo with separate agent modules, a master orchestrator, Groq-powered intent/planning/response steps (optional API key), TF-IDF retrieval-augmented answers over policy documents, PostgreSQL records, a standalone MCP server, tickets, SLA targets, and an observable agent event log.

> Demo scope: seeded fictional customers/orders only. Refund eligibility is checked, but no real payment provider is connected. SLA values are demonstration targets, not contractual guarantees.

## Requirements
- Python 3.11 (recommended)
- Node.js 20+ and npm
- Docker Desktop (recommended for PostgreSQL)
- Groq API key from https://console.groq.com/keys (the app still runs with deterministic fallback when missing)

## Fast setup (Windows PowerShell or VS Code terminal)

1. Copy `.env.example` to `.env` in the project root and paste your Groq key into `GROQ_API_KEY`.
2. Start PostgreSQL from the project root:

   ```powershell
   docker compose up -d postgres
   ```

3. Backend terminal:

   ```powershell
   cd backend
   py -3.11 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```

   If your terminal is Command Prompt, activate with `.venv\Scripts\activate.bat`.

4. Frontend terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

5. Open the Vite URL printed in the terminal (normally http://localhost:5173). API health: http://localhost:8000/api/health.

If Docker/PostgreSQL is unavailable for a quick local test, change `DATABASE_URL` in `.env` to `sqlite:///./aegissupport_dev.db`. PostgreSQL remains the intended project database.

## Run the MCP server separately
Open another backend terminal after installing requirements:

```powershell
cd backend
.venv\Scripts\activate
python -m mcp_server.server
```

The MCP server exposes `lookup_order`, `refund_eligibility`, `request_return`, `cancel_eligible_order`, and `account_status`. The FastAPI demo uses the same guarded business-tool implementations in-process; the standalone MCP endpoint is provided for MCP client/Inspector demonstrations. For production, connect the orchestrator through an MCP client transport rather than calling tool functions in-process.

## Demo customer and order IDs
- C001 — Aarav Mehta (Premium): `ORD12345` wrong delivered item, `ORD33410` processing order.
- C002 — Diya Shah (Standard): `ORD12006` shipped order.
- C003 — Kabir Rao (Premium): `ORD44100` annual plan.
- C004 — Mira Iyer (Standard): `ORD22001` payment debited but order unconfirmed.
- C005 — Ishaan Patel (Gold): `ORD12007` wrong delivered hub.

## Dataset to download (recommended: one dataset only)
Download the **Bitext Customer Support / Training Dataset for Chatbots & Virtual Assistants** from Kaggle:
https://www.kaggle.com/bitext/training-dataset-for-chatbotsvirtual-assistants
It contains over 20,000 customer-support utterances with intent labels and category groups. It is suitable for intent classification tests and benchmark evaluation; it is not a customer/order database and should not be used as a source of policy truth.

1. Download the CSV from Kaggle and place it in `data/raw/`.
2. Normalize it with:

   ```powershell
   cd ..
   python scripts/normalize_bitext.py data/raw/YOUR_DOWNLOADED_FILE.csv
   ```

3. The normalized evaluation data is written to `data/processed/customer_support_intents.csv`.

The demo's business records are fictional seeded records in PostgreSQL; the RAG knowledge base is `data/knowledge_base/articles.json`. This keeps the query dataset, operational records, and policy documents separate.

## Architecture
- `frontend/`: React JSX customer support workspace, supervisor dashboard, ticket queue, agent event trace, KB browser and security lab.
- `backend/agents/`: each specialist agent is implemented in its own Python module.
- `backend/orchestrator/master_orchestrator.py`: sequences agents, manages branching and persists trace events.
- `backend/mcp_server/`: MCP server exposing typed business tools.
- `backend/rag/`: retrieves policy chunks using TF-IDF as a lightweight local retrieval baseline. This is a retriever-grounded RAG implementation; embeddings can be added later without changing the agent contracts.
- `backend/db/`: SQLAlchemy models and demo seeding.

## Performance and measurement

- TF-IDF policy retrieval builds one reusable index and caches repeated query/intent pairs with a bounded TTL cache. Cache and request/LLM/database timing counters are available from the supervisor-only `/api/metrics` endpoint.
- High-confidence rule-based intents use local routing by default (`DETERMINISTIC_INTENT_ROUTING=true`), avoiding an unnecessary Groq request. Unmatched text still uses the configured model.
- Groq requests use an explicit timeout, one retry, and a bounded concurrency semaphore. Provider failures fall back to the existing deterministic agent behavior.
- Run `python scripts/benchmark_performance.py` from the project root to generate `reports/performance_benchmark.json` and `reports/PERFORMANCE_EVALUATION.md`. The benchmark uses the same fixed queries and KB for the pre-optimization and optimized TF-IDF paths and does not fabricate provider measurements.
- The current system does not run a local embedding model, so FP32/FP16/INT8 quantization and embedding distillation are not applicable. Groq-hosted models cannot be quantized or configured for speculative decoding, tensor parallelism, or pipeline parallelism through this API. Those techniques remain future options only for a self-hosted model deployment.

## Important implementation notes
- Set `GROQ_API_KEY` only in `.env`; never commit it.
- The model is configured with `GROQ_MODEL` in `.env` (default `llama-3.3-70b-versatile`). Confirm model availability in your Groq console if the provider changes model availability.
- If Groq is missing or errors, the app uses deterministic fallbacks for a reliable demo.
- Security checks are baseline demonstration controls, not production-grade authentication or a full adversarial defense system.
- Ticket SLA displays are targets; overdue computation and outbound notifications are not yet a full production SLA engine.
