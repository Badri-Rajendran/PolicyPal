# Chat redesign — the approved mockups

Approved on 2026-09-26. This folder is a snapshot of the design canvas
<https://claude.ai/artifact/KzwJcQggBJjZsSTxUuVUu3> (private to its owner). It is
the visual reference for the spec,
[docs/superpowers/specs/2026-09-26-chat-redesign-design.md](../../superpowers/specs/2026-09-26-chat-redesign-design.md).

The `.dc.html` files are the canvas's artboards. They run only inside the
canvas, which supplies `support.js`, so open the canvas link to click through
them. Read the files for exact markup and copy. `tokens.css` is the stylesheet
every artboard inlines; the frontend's tokens come from it.

| Artboard | Shows |
| --- | --- |
| `Main.dc.html` | An answered thread: the plan table, citation seals, the Sources panel, copy |
| `MainDark.dc.html` | The same, in the dark theme |
| `Streaming.dc.html` | An answer streaming in: progress steps, the caret, Stop; the sidebar hidden |
| `Empty.dc.html` | A new question: starter questions, the composer focused |
| `SidebarSearch.dc.html` | Searching the threads |
| `SidebarRename.dc.html` | Renaming a thread inline, and confirming a delete |
| `SidebarAccount.dc.html` | The account menu: profile, theme, shortcuts, sign out |
| `Mobile.dc.html` | A phone: the profile nudge, and a source open as a bottom sheet with its Wikipedia credit |
| `SignIn.dc.html` | Sign in, beside an example cited answer |
| `Profile.dc.html` | The profile form inside the app shell |

Plan names, prices and quoted passages are real public data from the local
catalog (2026 Covered California, San Diego County, age 40), used as sample
content. `you@example.com` is a placeholder.
