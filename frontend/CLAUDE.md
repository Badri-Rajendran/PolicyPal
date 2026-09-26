# Frontend Instructions

Vite + React 19 app in plain JSX. Follow the repository rules in [../CLAUDE.md](../CLAUDE.md) as well.

## Commands

```sh
npm install      # install dependencies
npm run dev      # vite dev server
npm run lint     # eslint
npm run build    # vite production build
npm run preview  # serve the build
npm test         # vitest
```

- Run `npm run lint` and `npm run build` after meaningful changes.

## Structure

Current layout — `components/`, `pages/`, `services/`, `features/`, `hooks/`, and `utils/` all
exist today.

| Path | Holds |
| --- | --- |
| `src/features/<domain>/` | Everything one domain owns: components, hooks, api, utils. |
| `src/pages/` | Thin route screens that compose features. |
| `src/components/` | Generic reusable UI only (Button, Input, Card). |
| `src/hooks/` | Custom hooks shared across the whole app. |
| `src/services/` | Network requests, API configuration, external integrations. |
| `src/utils/` | Pure JavaScript helpers, no React imports. |

- `features/chat/` is split by area: `sidebar/`, `transcript/`, `sources/`, `composer/`, with
  `AppShell`, `ChatHeader` and the `useMessages` / `useThreads` / `useSidebarHidden` hooks at its root.
- Visual markup, class names and copy come from `docs/design/chat-redesign/*.dc.html`; the design
  tokens (`--paper`, `--sheet`, `--ink`, `--seal`, `--pine`, …) live in `src/index.css`, light on
  `:root` and dark under `prefers-color-scheme` and `:root[data-theme="dark"]`. Each area imports
  its own CSS file.
- Organize by domain first: a feature owns its code and exposes a small public surface.
- Promote code into a global folder only when a second feature actually needs it.
- Give a component its own folder once it outgrows one file (component, styles, test, `index.js`).

## React practice

- Layer strictly: JSX/CSS for presentation, custom hooks for state and logic, `services/` for the
  outside world.
- Keep components presentational; move fetching and orchestration into hooks or services.
- Use `useEffect` only to sync with something external — never for derived state or event handling.
- Merge state that always changes together into one value (a `status` string, not `isSending` +
  `isSent`) so impossible UI states cannot exist.
- Add `React.memo`, `useMemo`, or `useCallback` only for a measured problem; by default they cost
  more than they save.
- Prefer composition and `children` over threading props through intermediate components.
- Keep dependencies lean: add a library only when the platform and existing code cannot do the job.
  Runtime dependencies are pinned to exact versions (`npm install --save-exact`).
- Answers are Markdown from the model: render them only through `AnswerBody` (no `rehype-raw`, no
  `dangerouslySetInnerHTML`); every link passes `safeUrl`, and one opening a new tab has
  `rel="noopener noreferrer"`.
- `localStorage` holds only the theme and the sidebar's hidden flag; wrap every storage access in
  try/catch.
- Motion runs inside `MotionConfig reducedMotion="user"`; the seal stamp is the only animation
  that runs on its own.
- Handle loading, empty, error, and success states explicitly.
- Use semantic HTML, labelled inputs, keyboard access, and visible focus states.

## Testing

- Vitest + React Testing Library, configured in `vite.config.js` with `src/setupTests.js`.
- One test file per component, colocated with it; cover render, user interaction, and
  loading/empty/error states.
- No component is done until its test passes.

## Principles

- SOLID: one responsibility per component and hook; split it when a second one appears.
- DRY: check `features/`, `components/`, `hooks/`, `services/`, and `utils/` before writing anything new.
- KISS: build the simplest thing that works; no abstraction before a second use case exists.
