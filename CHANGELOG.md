# Changelog

## Unreleased

- Add lightweight contextual retrieval: index each chunk's text prefixed
  with its article title/section (a dead `contextualized_text` field was
  already scaffolded for this), so a chunk that never names its topic by
  itself still matches on keyword and semantic search. Raw chunk text
  stored/shown is unchanged.
- Wire `chunk_overlap`/`chunk_size` config into the actual chunker (they
  were previously hardcoded and silently ignored) and raise the default
  overlap to 50 tokens (~15%) so a definition and its qualifying clause
  don't get severed across a chunk boundary.
- Add the chat frontend (React 19, Vite): sign in/register, a thread sidebar,
  and a message transcript with footnote-style source citations. Design is a
  deliberate "policy document" identity (paper/brass palette, IBM Plex
  Serif/Sans) rather than a generic chat-bubble look.
- Add Vitest + React Testing Library; 75 tests across every component and
  hook (render, interaction, loading/empty/error states).
- Fix a real race condition found while browser-testing the new UI: sending
  the first message in a brand-new thread kicked off the message-history GET
  and the send's POST concurrently; the GET (fast, empty) would resolve
  after the optimistic user message was added and silently erase it. Fixed
  by never letting the fetch overwrite messages a send already added, with
  a regression test that reproduces the exact ordering.
- Update README to match the real stack and structure (Flask, plain JSX,
  actual folders and Make targets) — it had drifted to describe an
  unbuilt FastAPI/TypeScript/LangChain design.
- Add a Flask API: JWT auth (register/login/me) and chat endpoints (threads,
  messages) that run the RAG pipeline and persist the conversation.
- Add row-level authorization on chat endpoints — a thread not owned by the
  requester returns 404, never 403.
- Add rate limiting (Flask-Limiter) on every endpoint, tightest on auth.
- Add security headers and strict CORS (single allowed frontend origin) to
  the API.
- Add `docs/decisions/0001-chat-api-auth.md` recording the auth/API design.
- Fix the RAG generation prompt: source chunks were being sent to the LLM
  with an internal `Chunk ID` field it didn't need (citations already come
  back separately in the API response), and a missing separator glued the
  context and the "think step by step" instruction into one run-on line.
- Switch the local LLM to `Qwen/Qwen2.5-0.5B-Instruct` and cap
  `max_new_tokens` at 256 — the previous 1.5B model exceeded this machine's
  RAM and caused swap thrashing that looked like a hang.
- Only select float16 on CUDA; fall back to float32 on MPS, whose fp16
  generation kernels are unreliable.
- Fix `search()` dropping weakly-relevant chunks: add `min_relevance_score`
  and filter reranked results below it before they reach the LLM.
- Fix `tokenizer.apply_chat_template(...)` missing `return_dict=True`,
  which meant generation crashed on every real call.
- Fix a `logger.info` call with no `%s` placeholder that raised inside the
  logging module on every generation.
- Fix `environment` config typo (`"productin"`) that made JSON production
  logging unreachable.
- Add real pytest coverage for retrieval and generation (previously two
  argparse scripts with no `test_`-prefixed functions — pytest silently
  collected zero tests from them).
- Add `scripts/ask.py` as the one CLI entry point for manually exercising
  the RAG pipeline.
- Deduplicate the ingestion pipeline's four repeated print-block stages into
  a `STAGES` loop.
- Add `users`, `threads`, and `messages` tables.
