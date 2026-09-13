# 0006 — Frontend routing: addressable threads

## Status

Accepted

## Context

`App.jsx` picks a screen from auth state and nothing else:

```jsx
return status === "signed-in" ? <ChatPage /> : <AuthPage />;
```

The whole app therefore lives at one URL. Three consequences, all of them
things a user expects to work:

- A conversation cannot be linked, bookmarked, or reopened. `selectedThreadId`
  is `useState` inside `useThreads`, so it exists only until the tab closes.
- Browser back and forward do nothing. Back from the chat screen leaves the
  application entirely.
- Sign-in and registration share a URL, so "create an account" cannot be
  linked to — which is the one link a product most often needs to send.

Session persistence (the change alongside this one) makes the gap more
obvious rather than less: a reload now keeps you signed in, and drops you on
an empty chat screen with the conversation you were reading still one click
away but no longer open.

## Decision

Adopt `react-router` and give the four screens real URLs:

| Route | Screen |
| --- | --- |
| `/login` | sign in |
| `/register` | create account |
| `/chat` | chat, no thread open |
| `/chat/:threadId` | that conversation open |

A route guard redirects signed-out visitors to `/login`, and sends a
signed-in visitor away from the auth routes.

`frontend/CLAUDE.md` says to add a library only when the platform and
existing code cannot do the job, so the alternative was taken seriously:
the History API is available, and four routes is not many. It was rejected
because the hand-rolled version is not the routing — it is everything
underneath it. Listening to `popstate`, keeping component state and URL in
sync in both directions, resolving the initial URL on mount, and not
double-pushing on a programmatic navigation is a well-known set of bugs with
a well-known solution. `react-router` is that solution, it is the default in
this ecosystem, and it is one dependency with no transitive weight worth
arguing about.

Root `CLAUDE.md` requires an ADR before adding a framework. This is that ADR.

### `selectedThreadId` moves into the URL

`useThreads` stops owning the selection. The open thread is a route param,
which is what makes it linkable, and the reason for the change rather than a
side effect of it. `useThreads` keeps the list and its mutations; selection
becomes navigation.

## Consequences

A conversation is now a URL that can be shared with someone who has access to
it, or reopened from history. Back and forward behave. `/register` can be
linked directly.

The route param is user-controlled input, so an unknown or malformed thread
id has to be handled as a real state rather than trusted: the API already
returns 404 for a thread that does not exist or belongs to someone else
(ADR 0001), and the UI shows the empty state rather than a broken screen.

A thread id in the URL is visible in history and in any shared link. It is a
UUID, not a secret, and every request for its contents is still authorised
server-side — but it does mean a link pasted somewhere public names a
conversation that exists, which a single-URL app did not.
