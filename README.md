# BizOS: Agentic AI Business Operating System

Phase 1 (foundation): FastAPI + Postgres + React/TS/Tailwind, with org-scoped auth.

## Layout

```
bizos/
  docker-compose.yml        Postgres 16 (pgvector image, ready for Phase 3)
  backend/
    app/
      main.py               FastAPI app, CORS, /health
      core/                 config, db session, JWT + password hashing
      models/               Organization, User (TenantMixin for org_id)
      api/                  deps.py (AuthContext), auth.py (register/login/me)
      schemas.py
    tests/                  pytest (SQLite, no Docker needed)
  frontend/                 Vite + React + TS + Tailwind
```

## Run

```bash
# 1. database
docker compose up -d db

# 2. backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set JWT_SECRET to a long random string
uvicorn app.main:app --reload --port 8000

# 3. frontend (new terminal)
cd frontend
cp .env.example .env
npm install
npm run dev
```

Check: `curl localhost:8000/health` returns `{"status":"ok","db":"ok"}`.
Open http://localhost:5173, create a workspace, you land on the dashboard shell.

## Test

```bash
cd backend && source .venv/bin/activate && pytest -q
```

## Tenancy rule (applies to every future table)

- Inherit `TenantMixin` (adds indexed `org_id` FK).
- `org_id` is read from the authenticated `AuthContext`, never from request bodies or URLs.
- Every query filters on `auth.org_id`.

## Knowledge base (Phase 3)

Upload or FAQ save -> parse (pdf/docx/txt/md/csv) -> chunk (~800 chars) -> embed -> store in `chunks` (pgvector) -> `POST /knowledge/search`.

- Embeddings run locally with fastembed (`BAAI/bge-small-en-v1.5`, 384 dims). The model downloads on first use (~130 MB).
- `EMBEDDING_PROVIDER=fake` is used by the tests. The provider sits behind `app/knowledge/embeddings.py`, so an API model can replace it.
- Postgres needs the `vector` extension. The app runs `CREATE EXTENSION IF NOT EXISTS vector` on startup (works on Neon).
- Every search filters on `org_id`.

## Sales Agent (Phase 4)

`POST /agents/sales/chat` runs: analyze (LLM, structured) -> search products + knowledge (this org only) -> reply (LLM, grounded on retrieved data only) -> escalation rules -> deterministic lead scoring -> save lead, messages and a step trace (`/agents/runs`).

- The LLM only reasons. Retrieval, scoring, escalation and persistence are plain code, so the agent can only do what is written there.
- Set `LLM_API_KEY` in `backend/.env` (free key from aistudio.google.com). Provider and model are `LLM_PROVIDER` and `LLM_MODEL`.
- `POST /demo/seed` (or the Dashboard button) loads a sample laptop store into an empty workspace.
- Free Gemini tier: prompts may be used by Google to improve products. Use demo data only until you switch to a paid tier or another provider (`app/llm/` is the only place to change).

## CRM and tools (Phases 5 and 6)

- Leads: filters, search, pipeline totals, detail page with conversation, notes, tasks, contact edits, mark won/lost/reopen.
- Tool calling (`app/tools/registry.py`): the model can only propose `create_quote`, `create_followup_task` or `draft_email`. Code validates args, takes prices and stock from the database, applies policy, and logs every call in `tool_calls`.
- Discounts above `AUTO_DISCOUNT_MAX_PCT` (5) or under `AUTO_DISCOUNT_MIN_QTY` (10) units wait in Approvals. Nothing is sent to customers; emails are drafts.

## Workflows (Phase 7)

Trigger (`lead.created`, `lead.hot`, `conversation.escalated`) + optional conditions + ordered steps (task, email draft, quote). Steps run through the same tool layer as the agent, so validation, policy and the approval gate all apply. Each workflow runs once per lead, and a failing workflow is logged without breaking the chat. Engine: `app/workflows/engine.py`.

## Automation (Phase 8)

A timer inside the API process (`SCHEDULER_INTERVAL_SECONDS`, default 300, 0 = off) fires the `lead.inactive` trigger for open leads. Condition `days_since_contact` decides who is quiet. Safe to overlap because a workflow runs once per lead. Phase 14 moves this to a separate worker.

## Human approval (Phase 9)

Per-org rules (`approval_rules`): auto-approved discount % and minimum units, a quote value limit, and tools that always need a human. They apply to the agent and to workflows. Only owners and admins can approve, reject (with a reason) or change the rules. The sidebar shows the pending count.

## Analytics agent (Phase 10)

The model never queries data or produces numbers. It picks 1 to 3 reports from a fixed catalog (`app/agents/analytics/metrics.py`), code runs them for the caller's org only, and the model words an answer from those results. The tables behind each answer are returned and shown. Anything outside the catalog gets an honest "can't answer". `GET /agents/analytics/overview` powers the dashboard with no AI.

## Support agent (Phase 11)

Answers policy questions (shipping, returns, warranty) from the knowledge base only. It can read an order only when the customer gives the order number and the email matches the order (see Customer features below); it has no access to payments or addresses. Refunds without a documented policy, angry customers, sensitive requests, unknown orders and "talk to a human" all escalate. Escalations (and issue categories like delivery, warranty, complaint) create a ticket (T-0001...). Later messages in the same chat update that ticket. Manage tickets on the Tickets page. Support and sales conversations are kept separate.

## Founder agent (Phase 12)

`app/agents/founder/snapshot.py` computes headline numbers and "attention items" in code (approvals waiting, hot leads with no contact, high priority tickets, overdue tasks, quiet leads, failed actions). The model only ranks existing items and writes a short summary. Any item id it invents is dropped. If the model is down, the briefing is built from the snapshot alone. Briefings are saved and the live list works with no AI.

## Integrations (Phase 13)

Per-org email (SMTP) and Slack webhook, configured on the Integrations page. Secrets are Fernet-encrypted in the database (key from `SECRETS_KEY`, or derived from `JWT_SECRET`; changing it makes stored credentials unreadable) and never returned by the API. SMTP hosts that resolve to private addresses are refused unless `ALLOW_PRIVATE_HOSTS=true`. Agents and workflows can only draft emails. An owner or admin sends a draft with the Send button on the lead page, which goes through the normal tool path (`send_email`, always human-decided, logged with who sent it) and cannot send the same email twice. Slack gets a message on pending approvals and new tickets, and a failing webhook never breaks an agent. WhatsApp is deferred.

## Production readiness (Phase 14)

**Migrations (Alembic).** The app no longer creates tables on Postgres. It refuses to start if the database is behind the code and prints the command to run.
- New database: `alembic upgrade head`
- Database created before Phase 14: `alembic stamp 0001` once, then `alembic upgrade head`
- After changing a model: `alembic revision --autogenerate -m "what changed"`, read the generated file, then `alembic upgrade head`. A test fails if models and migrations drift apart.

**Sessions.** The browser holds only httpOnly cookies: a 15 minute access token and a 14 day refresh token. Refresh tokens are stored hashed, rotate on every use, and replaying an old one revokes the whole login. Logout revokes it server side. Cookie requests that change data must come from an origin in `CORS_ORIGINS`. API clients can still send `Authorization: Bearer`.

**Rate limits** (in memory, per API process): login 20/min per IP and 8 per 5 min per account, register 10/hour per IP, LLM endpoints 30/min per org. Move to Redis if you run several API instances.

**Scheduler.** Run it as its own process with `python -m app.worker` and set `RUN_SCHEDULER_IN_API=false` on the API. Run exactly one worker.

**Production switch.** With `ENVIRONMENT=production` the API refuses to start unless `JWT_SECRET` is strong, `COOKIE_SECURE=true`, `ALLOW_PRIVATE_HOSTS=false` and `CORS_ORIGINS` lists real URLs. Every request gets an `X-Request-ID` and an access log line.

Uploaded originals are written to local disk but only the extracted text is used afterwards, so an ephemeral disk on a host loses nothing that matters.

## Customer chat and Inbox

Each business gets a public page at `/chat/<slug>` (off until the owner turns it on under Settings, Customer chat). A customer picks "I want to buy" or "I need help", gives a name and email, and talks to the sales or support agent. The business gets the same leads, tickets, approvals and Slack alerts as before.

- A customer's only credential is a signed visitor token (one conversation, 30 days, a different audience from staff tokens, so neither works as the other). Responses contain chat text, a hand-off flag and a ticket reference, never scores, notes, steps or sources.
- Limits: 20 messages per minute per IP, 10 per minute per conversation, 400 per hour per business, 60 customer messages per conversation, 20 new chats per hour per IP.
- Inbox: staff see customer chats, read them and reply. The first reply takes the chat over (`human_active`): the AI stays quiet and an open ticket moves to in progress. "Hand back to the AI" returns control. The customer's page polls every 4 seconds, so replies show up live.
- Embedding: an iframe snippet is shown on the settings page. A script-tag widget is not offered because it would need per-site CORS rules.

## Customer features

Set `PUBLIC_APP_URL` in `backend/.env` to your frontend URL (default `http://localhost:5173`). It is used for the links in emails and chat, and must be `https://` in production.

- **Reply emails.** The page pings the API on every poll. If a staff member replies and the customer has not polled for 20 seconds, they get an email with the reply and a link that reopens the same chat (`/chat/<slug>?t=<token>`, the token is removed from the address bar). At most one such email per 5 minutes per chat. Needs Email under Integrations. The Inbox tells the replying person what happened (emailed, customer online, email not connected, failed).
- **Quote link.** A quote becomes reachable at `/quote/<token>` once it is sent: automatically for a quote the agent created without needing approval, after approval for one that needed it, or with "Send to customer" on the lead page (owner/admin). The customer sees the items and total and can accept, decline or ask for changes (note required). The response is stored on the quote, added to the lead as a note, becomes a task for the team, and pings Slack. Accepting does not mark the lead as converted, a person decides that. Links expire after 14 days and only one response is accepted.
- **Order status.** Add orders under Support, Orders (or import a CSV). The support agent looks an order up in code, never the model: the order number and the email on the chat must both match. The model only gets status, carrier, tracking, expected delivery and item names (no price, address or payment). Not found and wrong email give the same answer and escalate to a person. After 5 failed lookups in one chat, lookups stop. The email comes from the chat form and is not verified by a code, so someone who knows both an order number and the buyer's email can see that order's status.
- **Hindi and Hinglish.** Both agents are told to answer in the language and script the customer writes in. The customer page has an English/Hindi toggle (it starts in Hindi if the browser is set to Hindi). Quality depends on the model, which is not covered by the automated tests.
- **Photos.** The camera button sends a JPG, PNG or WebP (shrunk in the browser to 1600px, 4 MB max on the server, 10 per chat, type checked from the file bytes). A photo always goes to a person: the chat is flagged, a support chat gets a ticket, Slack is pinged and the customer gets a fixed acknowledgement. The AI does not look at images. Photos are stored in the database (the host disk is not durable) and are served only to the customer who sent them and to staff of that business.
- **Chat transcript.** "Email me this chat" sends the conversation to the email the customer gave when starting (3 per hour per chat). Only shown when Email is connected.

## Home screen and speed

- Home (`GET /home/today`) builds the owner's day from real data: chats waiting, approvals, customer quote answers nobody has followed up, urgent tickets, hot leads, plus a setup checklist computed from what exists (profile, products, FAQs, chat on, a test chat, email, orders). The sidebar counters use one request (`GET /home/counts`).
- The look is set in `frontend/src/index.css` (colours and fonts). Redefining the slate and indigo scales there restyles every page.
- If the database is far from the API, every query costs a round trip. Keep them in the same region. Auth is one query, and Postgres connections time out after 10 seconds instead of hanging.

## Known shortcuts

- Rate limiting is per process (see above).
- WhatsApp is not built.
- Photos are not analysed by the AI, a person looks at them.
- Order lookup trusts the email typed in the chat form (no verification code).
- Emails to customers are in English, even when the chat is in Hindi.

## Author & Contact

Developed by **Vinayaka N Walishettar**  
LinkedIn: [https://www.linkedin.com/in/vinayaka-n-walishettar/](https://www.linkedin.com/in/vinayaka-n-walishettar/)

