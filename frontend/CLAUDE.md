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
