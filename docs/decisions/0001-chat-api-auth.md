# 0001 — Chat API and authentication design

## Status

Accepted

## Context

The RAG pipeline (retrieval + generation) works but is only reachable from a
CLI script. To back a browser chat UI, PolicyPal needs an HTTP API that can
authenticate a user and let them hold multi-turn conversations backed by the
`threads`/`messages` tables already in the schema.

The frontend is a separate Vite dev server (`localhost:5173`) calling a
Flask API (`localhost:5000` in dev) — a decoupled SPA + API, not
server-rendered pages.

## Decision

- **Stateless JWT bearer auth**, not cookie sessions. The access token is
  returned in the JSON login/register response and sent by the frontend as
  an `Authorization: Bearer <token>` header. Because the browser never
  attaches this header automatically the way it does a cookie, requests
  forged from another site carry no credential — CSRF protection is
  structurally unnecessary here rather than a control we chose to skip.
  `flask-jwt-extended` issues and verifies the tokens; access tokens expire
  after 30 minutes (`jwt_access_token_expires_minutes`).
- **Passwords hashed with `bcrypt`** directly (no ORM plugin) — one function
  call on write, one on read, nothing to configure.
- **Strict CORS**: only `settings.frontend_origin` is allowed, via
  `flask-cors`. No wildcard origins.
- **Flask-Limiter** rate-limits every route; auth endpoints (register/login)
  get the tightest limits since they're the classic brute-force target.
- **Security headers** (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) are set in an `after_request` hook in the app factory,
  applied globally rather than per-route.
- **Authorization is row-level, not role-based**: a user can only ever see
  their own threads/messages. A request for another user's thread returns
  404 (not 403), so the API never confirms whether a given thread ID exists
  for someone else.
- **App factory pattern** (`create_app()` in `src/api/main.py`) so tests can
  build an isolated app instance instead of importing a module-level
  singleton.

## Consequences

- No refresh-token flow yet: a user is logged out when the access token
  expires or the tab is closed (the token lives in memory in the frontend,
  never `localStorage`, to limit what an XSS bug could exfiltrate). This is
  an accepted v1 tradeoff, not an oversight — revisit if session length
  becomes a real complaint.
- Because CSRF doesn't apply, no CSRF token is issued or checked anywhere in
  this API. If a cookie-based flow is ever added, this decision must be
  revisited.
