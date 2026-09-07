# Changelog

## Unreleased

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
