# Chat redesign — design

**Status:** approved design, spec for review · **Date:** 2026-09-26 · **ADR:** 0027
**Mockups:** [docs/design/chat-redesign/](../../design/chat-redesign/README.md) (canvas <https://claude.ai/artifact/KzwJcQggBJjZsSTxUuVUu3>)
**Branches and PRs:**

1. `feature_chat_redesign_api`: the backend and the docs.
2. `feature_chat_redesign_ui`: the frontend, built on the contracts in section 3.

## 1. Problem

The chat works, but it reads like a prototype.

- **Answers are raw text.** The model writes Markdown with `[Source: …]` and
  `[Plan: …]` markers, and all of it shows literally.
- **Sources are a bare list.** Each is a file name and a match score, with no
  way to see the text an answer relied on.
- **Answers arrive all at once** after a long wait, behind three pulsing dots.
- **Threads can't be renamed or searched.**
- **There is no dark-mode choice and no keyboard shortcuts.** On a phone the
  sidebar takes 40% of the screen.

## 2. Decisions (user, 2026-09-26)

| Topic | Decision |
| --- | --- |
| Visual direction | Evolve the current identity: paper, ink and brass, with IBM Plex |
| Screens | Chat, plus sign-in, register and profile |
| Backend features | Streaming answers, renaming threads, showing source passages, and every frontend-only interaction |
| Libraries | `lucide-react`, `motion`, `react-markdown` and `remark-gfm`, pinned to exact versions |
| Passage length | A brief quote of ≤300 characters plus a link. SBC text stays within ADR 0013's "quote briefly". Wikipedia text carries its CC BY-SA credit. |
| Stop | Cancels the answer. The question stays in the thread, as it does on a failed answer; nothing partial is saved. |
| Quote choice | The part of the passage that best matches the answer, not its first 300 characters |
| Theme | System, Light or Dark, remembered per browser; System is the default |
| Process | This spec, then an implementation plan, both reviewed. Then build, with one agent for the backend and one for the frontend. |
| PRs | Backend first, then frontend |

## 3. Backend (PR 1)

### 3.1 Renaming a thread

`PATCH /api/chat/threads/<thread_id>`, JWT, **30 per minute**.

- **Body:** `ThreadRenameRequest { title: str }`. The title is stripped, and
  must then be 1–200 characters. Blank, or over 200, returns 422.
- **Ownership:** the existing `_get_owned_thread`. A missing thread, someone
  else's thread, or a malformed id returns 404.
- **Returns** 200 with the `ThreadResponse`.
- **It does not change `updated_at`.** `updated_at` means the thread's last
  activity, and orders the list, so renaming must not move a thread to the
  top. Issue an explicit `UPDATE threads SET title = :t, updated_at =
  threads.updated_at` rather than setting the attribute, because the column's
  `onupdate` would otherwise fire.

### 3.2 Source passages

**Schema** (a migration after head `3b1d6e2a9c47`):
`message_sources.content_sha256 String(64) NULL`. It holds the SHA-256 (hex)
of the passage text as the answer used it. It is set on every new answer, and
older rows keep NULL. Chunks are rebuilt in place (ADR 0007): the same
`chunk_id` can later hold different text, and the hash is how the endpoint can
tell.

**`SourceResponse` gains `id`,** the `MessageSource` UUID. Both message
endpoints return it.

**`GET /api/chat/sources/<source_id>`, JWT, 60 per minute.**

- **Ownership.** Join `MessageSource → Message → Thread` and require
  `Thread.user_id = current user`. Anything else, or a malformed id, returns
  404, never 403. Chunk ids are guessable, so there is deliberately no lookup
  by chunk id.
- **Lookup.** A `chunk_id` starting `sbc_` is read from `sbc_chunks`, joined to
  `sbc_documents`. Anything else is read from `chunks`.
- **Status:**

  | `status` | When | `quote` |
  | --- | --- | --- |
  | `ok` | The hash is stored and matches the text now | the excerpt |
  | `unverified` | The hash is NULL (an older answer) and the chunk exists | the excerpt; the UI says it may have changed |
  | `changed` | The hash is stored and does not match | `null` |
  | `missing` | No such chunk now | `null` |

- **Response:**

  ```json
  {
    "id": "uuid",
    "kind": "sbc | wikipedia | healthcare_gov | other",
    "title": "Sharp Silver 70 Premier HMO",
    "document": "Summary of Benefits and Coverage, 2026",
    "section": "If you need immediate medical attention",
    "quote": "Urgent care | $50 copay/visit; deductible does not apply | …",
    "status": "ok",
    "url": "https://…pdf",
    "license": null
  }
  ```

- **Per kind.** Every field is derived by server code, never by the model.

  | kind | Recognised by | `title` | `document` | `url` | `license` |
  | --- | --- | --- | --- | --- | --- |
  | `sbc` | `chunk_id` prefix `sbc_` | The plan name: the label before ` - Summary of Benefits - ` | `Summary of Benefits and Coverage, {plan_year}` | `sbc_documents.url`, if `safe` | `null` |
  | `wikipedia` | Label `wiki_{Title}.txt` | The title, with underscores as spaces | `Wikipedia article` | `https://en.wikipedia.org/wiki/{Title}`, URL-quoted | `{name, url}` from the registry entry `wikipedia` (CC BY-SA 4.0) |
  | `healthcare_gov` | Labels `hcg_glossary_{T}.md` and `hcg_article_{T}.md` | T | `HealthCare.gov glossary` or `HealthCare.gov article` | `null` (not stored) | `null` (public domain) |
  | `other` | Anything else | The label without its extension | `null` | `null` | `null` |

  `section` is `sbc_chunks.section` for an SBC, and `null` otherwise. A URL is
  returned only if it is `https://` and passes the existing unsafe-URL check
  (`src/ingestion/sbc/fetch.py` `unsafe_reason`). Otherwise it is `null`.
- **Excerpt** (`src/services/passages.py`, pure functions):
  - Split the passage into segments: lines, then sentences within a line.
  - Score each segment by how many distinct lower-cased words of ≥3 letters it
    shares with the assistant message's text, leaving out a short stop-word
    list. Ties go to the earlier segment.
  - Start at the best segment and add the segments after it while the total
    stays within **300 characters**.
  - A segment longer than 300 is cut at the last space before 300.
  - Prefix `… ` when the excerpt doesn't start at the passage's start, and
    suffix ` …` when it doesn't reach the end.
  - A passage of ≤300 characters is returned whole.

### 3.3 Streaming answers

**`POST /api/chat/threads/<thread_id>/messages/stream`**, JWT. It has the same
body as `POST …/messages`.

- **The rate limit is shared.** Both send routes use
  `limiter.shared_limit("15 per minute", scope="chat_send")`, so one user can't
  double their rate by using both.
- **Before the stream, as today, returning ordinary JSON errors:**
  - 401 for the session;
  - 404 for ownership;
  - 422 for the body;
  - 429 for the limiter, and 429 `daily token budget exhausted` for the budget.

  Then the user's message is added and **committed**, so no transaction is held
  open while the model runs.
- **Response:** `200 text/event-stream`, with `Cache-Control: no-cache` and
  `X-Accel-Buffering: no`, wrapped in `stream_with_context`. Each event is
  `event: <name>\ndata: <json>\n\n`.

  | Event | Data | Meaning |
  | --- | --- | --- |
  | `user_message` | `{message: MessageResponse}` | The saved question. It replaces the optimistic one. |
  | `stage` | `{stage}`: one of `understanding`, `searching`, `plans`, `coverage`, `writing` | Progress. `understanding` is sent only when history triggers a rewrite. `plans` is sent before a `search_plans` call, `coverage` before `plan_coverage`, and `writing` just before the first `delta`. |
  | `notice` | `{text}` | A server-written notice (ADR 0024, 0026), sent as soon as a tool returns it |
  | `delta` | `{text}` | Answer text to append |
  | `reset` | `{}` | Discard every delta so far: a round that had streamed text went on to call a tool |
  | `done` | `{message: MessageResponse, thread: ThreadResponse}` | The authoritative saved answer: notices plus text, sources, plans and title. The client renders this and drops its draft. |
  | `error` | `{error: "generation failed"}` | The model failed. The question stays and nothing is saved, as with today's 502. |

- **Generation refactor** (`src/services/generation.py`):
  - **Events.** `answer_events(query, chunks, history, profile, shown_plans, *,
    stream: bool)` is a generator. It yields event dataclasses (`Stage`,
    `Notice`, `Delta`, `Reset`) and last of all `Done(answer)`.
  - **Wrappers.** `answer()` drains `answer_events(stream=False)` and returns
    the `Answer`. `answer_query_events()` yields `Stage("understanding")` when
    it rewrites and `Stage("searching")` before `search`, then delegates.
    `answer_query()` drains that. The CLI, the evals and every existing test
    keep calling `answer`/`answer_query` unchanged.
  - **The tool loop is shared.** Only the completion call differs.
    `stream=False` uses today's `_complete`. `stream=True` uses a new
    `_complete_stream`, which:
    - calls `create(..., stream=True, stream_options={"include_usage": True})`;
    - yields `Delta`s;
    - puts tool-call deltas together by index;
    - adds the usage from the final chunk to `_tokens_used`, and warns when
      usage never arrives;
    - returns the assembled message with `content`, `tool_calls` and
      `finish_reason`.
  - **Deltas are only forwarded once the answer is grounded,** meaning
    `chunks or searched`. Before that, text is buffered, so the "no chunks and
    no search → NO_ANSWER" path never has to take back text already shown. If
    a round that streamed text then calls tools, `Reset` is yielded.
  - **The rest is unchanged:**
    - the empty-answer fallback;
    - coverage-citation filtering;
    - notices put before the final text;
    - `_distinct`.

    All of it happens before `Done`, so `done` always carries exactly what the
    JSON route would have saved.
- **Persisting** is shared by both routes in one helper, `_save_answer(db,
  thread, body, result)`:
  - the assistant message;
  - its sources, with `content_sha256`;
  - its plan snapshots;
  - the automatic title.

  After `Done`, the stream saves the answer, calls `record_tokens`, commits,
  then sends `done`.
- **Failures and cancelling.**
  - On `openai.OpenAIError`: record the tokens, commit, send `error`, and end.
  - In a `finally`, which also covers a client disconnect (`GeneratorExit`):
    record any spend not yet recorded, exactly once, and commit. No assistant
    message is saved.
  - Errors are logged with the thread id only, never content.
- **Serving.** Gunicorn stays at 1 worker and 8 threads (ADR 0022); an open
  stream holds one thread, as a request does today. The ADR records that
  Azure's ingress timeout (~240 s) exceeds the worst case (3 rounds, 30 s
  model timeout).
- **The JSON route stays.** It is used by scripts and existing tests, and it is
  the fallback. The frontend switches to the stream.

### 3.4 Security (OWASP)

- **Authorization is checked on every new route.** Ownership failures return
  404, and passages are reachable only through the user's own
  `MessageSource` ids.
- **Parameterised SQLAlchemy only.** New request bodies use Pydantic with
  length limits.
- **No content in logs.** Nothing logs question or answer text, passages, ZIP
  codes or ages; logs carry ids and lengths.
- **The stream sends only what `done` would.** Deltas are model output the
  client renders as Markdown without raw HTML (section 4.4). The model can't
  add a field to an event, because every event is built by server code.
- **Quotes are brief and links are safe.** Passage text is quoted briefly,
  keeping to ADR 0013 and the licences, and every URL is `https://` only and
  passes `unsafe_reason`.

### 3.5 Tests (PR 1)

- **`test_chat.py`, rename:**
  - 200, and the new title is shown in the list;
  - the list order is unchanged (`updated_at` not bumped);
  - whitespace is stripped;
  - 422 for a blank or 201-character title;
  - 404 for another user's thread, a missing id or a malformed id;
  - 401 with no token.
- **`test_chat.py`, sources:**
  - an `id` is in both message endpoints' sources;
  - `GET` for `ok` (SBC, Wikipedia, HealthCare.gov), `unverified`, `changed` and
    `missing`;
  - another user's source returns 404;
  - an unsafe or `http` URL becomes `null`;
  - the Wikipedia licence comes from the registry;
  - the hash is written on new answers.
- **`test_passages.py`:**
  - the excerpt picks the segment that best matches the answer;
  - the 300-character cap;
  - the ellipses;
  - a passage of 300 characters or fewer is returned whole;
  - a single long line;
  - ties go to the earlier segment;
  - empty inputs.
- **`test_chat_stream.py`** (patching `answer_query_events`):
  - the event order for the happy path;
  - `done` matches what was saved;
  - the user message is committed before any model event;
  - 404, 422 and 429 (budget) come back as JSON before the stream;
  - `error` on `OpenAIError`, with the user message kept and tokens recorded;
  - a disconnect (closing the generator) records tokens once and saves no
    answer;
  - the headers.
- **`test_generation.py`** (a fake streaming client yielding chunk objects):
  - `answer_events(stream=True)` gives the same `Answer` as `stream=False`;
  - deltas arrive in order;
  - `Reset` when a streamed round turns into tool calls;
  - no deltas before grounding (the NO_ANSWER path);
  - stages and notices;
  - usage counted, and a warning when it is missing;
  - tool-call fragments put together.
- **`test_rate_limits.py`:**
  - the rename is limited at 30 per minute;
  - the source lookup at 60 per minute;
  - the stream at 15 per minute, and **shared** with the JSON send (8 + 8
    requests → the 16th is 429);
  - each 429 carries `Retry-After`.
- **`test_models_chat.py` / `alembic check`:** the new column. The migration
  round-trips (upgrade, downgrade).

## 4. Frontend (PR 2)

### 4.1 Tokens and theme

`src/index.css` takes its tokens from `docs/design/chat-redesign/tokens.css`,
the `.pp` palette:

- **Light:** paper `#E8E5DB`, sheet `#F8F6F0`, ink `#1E211C`, ink-soft
  `#575D51`, rule `#D6D0BF`, seal `#96651F`, pine `#2C5B4B`.
- **Dark:** as in the `.pp.dark` block.
- **Type:** IBM Plex Serif for questions and headings, IBM Plex Sans for body
  text, and tabular figures for money.

The theme is set on `<html data-theme>`:

- `:root` holds the light palette;
- `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`
  holds the dark one;
- `:root[data-theme="dark"]` holds it too.

`hooks/useTheme.js` reads and writes `localStorage["policypal.theme"]`
(`system`, `light` or `dark`). Every storage access is wrapped in try/catch,
because storage can be unavailable.

### 4.2 Structure

These files are new or rewritten. Every component gets a colocated
`*.test.jsx`.

```
components/            Button (primary|ghost|danger|icon), IconButton, Menu (menu button + items, arrow keys, Esc),
                       TextField (+ password show/hide), ErrorBanner, Toast
hooks/                 useTheme, useShortcuts (Ctrl/⌘K, /, Esc), useMediaQuery
features/chat/
  AppShell.jsx         sidebar + main (+ sources panel); collapsible sidebar; on ≤720px the sidebar is a drawer
  sidebar/             Sidebar, ThreadSearch, ThreadGroup, ThreadListItem (menu → Rename inline | Delete confirm inline),
                       AccountMenu (profile, theme radio group, shortcuts, sign out)
  transcript/          Transcript (pairs messages into exchanges; stick-to-bottom; JumpToLatest), Exchange (question as
                       heading + answer), AnswerBody (react-markdown + remark-gfm + remarkMarkers), Seal, PlanRef,
                       AnswerFooter (source chips, Copy), StreamingAnswer (ProgressSteps + text + caret), EmptyState
  sources/             SourcesPanel (desktop column / phone bottom sheet), SourceCard, useSource (fetch + cache)
  composer/            Composer (autosize, send/stop, hints), ProfileNudge
  useMessages.js       load, stream send, stop (AbortController), events → state
  useThreads.js        + renameThread
features/plans/        PlanComparison restyled: numbered rows, "Ask about this plan", row flash from PlanRef
features/auth/         AuthPage split layout with the example cited answer; AuthForm restyled
features/profile/      ProfilePage inside AppShell; ProfileForm restyled; "Where this goes" aside
services/              chatService: streamMessage, renameThread, getSource; sse.js (a fetch ReadableStream parser)
utils/                 markers.js (remark plugin + copy-text), threadGroups.js (Today / Previous 7 days / Earlier),
                       exchanges.js
```

### 4.3 Behaviour

- **Sending:**
  - Enter sends and Shift+Enter adds a line.
  - The send button becomes Stop while an answer streams. Esc or Stop aborts
    the fetch, the draft answer is removed, and the thread shows "You stopped
    this answer." with an "Ask again" button.
  - **Errors that come before the stream:**

    | Error | Handled as |
    | --- | --- |
    | 401 | an expired session, as today |
    | 429 | today's two messages |
    | 422 or 404 | the error banner |
- **Progress:** `stage` events drive the progress steps. Each code maps to
  wording: "Understanding your question", "Searching the references",
  "Searching plans near you", "Reading Summaries of Benefits", "Writing the
  answer". Finished steps are ticked.
- **Markdown and markers:**
  - `react-markdown` with `remark-gfm`, with raw HTML never rendered. Links go
    through `utils/safeUrl` and open in a new tab with `noopener noreferrer`.
  - `remarkMarkers` turns each `[Source: a; b]` into seals. A seal's number is
    the matching source's position in `message.sources`, which the API orders
    by relevance. A label with no matching source is left out.
  - `[Plan: id]` becomes a `PlanRef` showing the plan's position and name from
    `message.plans`. An id not among them is left as its text.
- **Seals:**
  - Clicking one opens the Sources panel on that source.
  - Hovering one outlines its source card.
  - When an answer finishes streaming, its seals stamp in (scale and rotate,
    with a stagger of 80 ms). This happens only for a live answer, never when
    history loads. It is the one self-running animation.
- **Sources panel:**
  - It lists the latest selected answer's sources. Each card's passage is
    loaded when the card is first shown, and cached per source id.
  - Each card shows the title, document, section, quote, a match meter (the
    relevance percentage), and a link: "Carrier's PDF" or "Read on Wikipedia".
  - Wikipedia text carries its licence credit.
  - `unverified` adds "This passage may have changed since the answer."
  - `changed` and `missing` say "This passage has changed since the answer and
    can't be shown."
  - On ≤720 px the panel is a bottom sheet with a scrim, and Esc closes it.
- **Plans:**
  - Rows are numbered 1…n in the order the answer showed them.
  - "Ask about this plan" puts `About plan {n}, {name}: ` in the composer and
    focuses it.
  - A `PlanRef` scrolls to its row and flashes it for 1.4 s.
  - Nothing marks a "best" plan (ADR 0010: compare, never recommend).
- **Copy:** copies the answer as plain text, with seals as `[n]` and plan refs
  as their names. It shows "Copied" for 1.6 s, or "Couldn't copy".
- **Sidebar:**
  - A search box filters thread titles as you type, case-insensitively, with
    the matches highlighted, and shows "No questions match".
  - Threads are grouped by `updated_at`.
  - Each thread's ⋯ menu has Rename, which edits inline (Enter saves, Esc
    cancels, a blank title is refused), and Delete, which asks for
    confirmation inline ("Delete" / "Keep it").
  - The header title can be renamed too.
  - The sidebar can be hidden, and the choice is remembered per browser.
- **Shortcuts:**
  - Ctrl/⌘K starts a new question.
  - `/` focuses the composer, when you're not already typing in a field.
  - Esc stops an answer, or closes the open menu, panel or sheet.
  - The account menu lists these.
- **Jump to latest:** appears when you are more than 200 px above the bottom.
  While you're at the bottom, a streaming answer keeps the view pinned there.
- **Empty state:** the design's heading and four starter questions. The two
  plan starters are labelled "Plans near you".
- **Motion:**
  - `motion` inside `MotionConfig reducedMotion="user"` (the CSS already
    respects `prefers-reduced-motion`).
  - Motion that answers an action: the panel and sheet sliding in, the sidebar
    collapsing, menus, and toasts.
  - The only motion that runs on its own is the stamp.
- **Accessibility:**
  - semantic landmarks, and real buttons and links;
  - `aria-live="polite"` on the streaming answer, with `aria-busy` while it
    streams;
  - focus moves into the panel, sheet and menus and back out when they close;
  - visible focus on everything;
  - text contrast ≥ 4.5:1 in both themes.
- **Sign-in and register:** the split layout. The left half shows the example
  cited answer, using the HealthCare.gov glossary text for Copayment and
  Coinsurance. Register keeps the ZIP and date-of-birth fields, as today.
- **Profile:** inside the app shell, with the "Where this goes" aside.

### 4.4 Frontend security

- **No raw HTML.** `react-markdown`'s default escaping stays on: there is no
  `rehype-raw` and no `dangerouslySetInnerHTML`.
- **Only safe links.** `https` URLs from answers, passages and plans pass
  `safeUrl`, and every link that opens a new tab has `rel="noopener
  noreferrer"`.
- **Only the theme and the sidebar's open state are stored locally.** No
  tokens or personal data.

### 4.5 Tests (PR 2)

- **Vitest and React Testing Library, for every component and hook:**
  - render;
  - interaction;
  - loading, empty, error and success states;
  - accessibility queries by role.

  Key cases:
  - the SSE parser on split chunks, several events per chunk, and a final
    event with no trailing blank line;
  - `useMessages`: the stream's event order, `reset`, `done` replacing the
    draft, `error`, and stop, which aborts and keeps the question;
  - the marker plugin: several labels in one bracket, an unknown label, and
    plan refs;
  - `threadGroups` at date boundaries;
  - rename and delete confirmation, driven by the keyboard;
  - search highlighting;
  - the source card in all four statuses and the Wikipedia credit;
  - the theme stored and applied;
  - shortcuts ignored while typing in an input;
  - the copy text.
- **Playwright (plugin), run by hand at the end against the local stack:**
  - sign in;
  - ask a plan question with a San Diego ZIP;
  - watch it stream;
  - open a seal's source;
  - rename and search threads;
  - switch to the dark theme;
  - a phone viewport, with its sheet;
  - Stop.

  Screenshots from the run go in the PR.

## 5. Documentation

- **ADR 0027:** streaming answers, the passage endpoint (hashes, brief quotes,
  licence credit), and rename semantics. It amends ADR 0007 (citations now
  carry a content hash) and ADR 0022 (streams hold a gthread thread).
  Sub-project 3's planned ADR moves to 0028.
- **README:** the chat features, the new endpoints and the new dependencies.
- **CHANGELOG:** bullets after every commit.

## 6. Out of scope

- Regenerating an answer.
- Feedback buttons.
- Editing a sent question.
- Sharing a thread.
- Saving a partial answer after Stop.
- Server-side thread search.
- HealthCare.gov passage URLs, which are not stored today.

## 7. Review focus (risks)

1. **A reset mid-answer.** The model starts writing, then calls a tool. The UI
   must clear the text cleanly, and `done` must match what was saved.
2. **A disconnect mid-stream.** Spend must still be recorded, and no
   half-written answer or open transaction left behind.
3. **The stamp must not replay.** On reloading a thread, seals must not stamp
   again, and old answers without a hash must say "may have changed", never
   show text silently.
4. **Two sends at once, from two tabs or double clicks.** The shared limit
   holds, and the composer is disabled while an answer streams.
5. **Narrow screens.** The plan table scrolls inside its own box, and the page
   never scrolls sideways at 390 px.
