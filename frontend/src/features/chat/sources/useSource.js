import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../../hooks/useAuth";
import { SessionExpiredError } from "../../../services/apiClient";
import * as chatService from "../../../services/chatService";

// Passages by MessageSource id, for this page's life. A passage is looked up
// once, however many cards show it; `pending` shares a request in flight.
const passages = new Map();
const pending = new Map();

// Signing out forgets them: they belong to that user's answers.
export function clearSourceCache() {
  passages.clear();
  pending.clear();
}

function load(token, sourceId) {
  if (!pending.has(sourceId)) {
    const request = chatService.getSource(token, sourceId).then(
      (passage) => {
        passages.set(sourceId, passage);
        return passage;
      },
      (err) => {
        pending.delete(sourceId); // a failure is not kept: retry asks again
        throw err;
      },
    );
    pending.set(sourceId, request);
  }
  return pending.get(sourceId);
}

function stateFor(sourceId) {
  return passages.has(sourceId)
    ? { status: "ready", passage: passages.get(sourceId) }
    : { status: "loading", passage: null };
}

// One cited passage (GET /api/chat/sources/<id>, spec §3.2), fetched when a
// card first shows it.
export function useSource(sourceId) {
  const { token, expireSession } = useAuth();
  const [state, setState] = useState(() => stateFor(sourceId));
  const [shownId, setShownId] = useState(sourceId);
  const [attempt, setAttempt] = useState(0);

  if (sourceId !== shownId) {
    setShownId(sourceId);
    setState(stateFor(sourceId));
  }

  useEffect(() => {
    if (!sourceId || passages.has(sourceId)) return undefined;
    let ignore = false;
    load(token, sourceId).then(
      (passage) => {
        if (!ignore) setState({ status: "ready", passage });
      },
      (err) => {
        if (ignore) return;
        if (err instanceof SessionExpiredError) expireSession();
        else setState({ status: "error", passage: null });
      },
    );
    return () => {
      ignore = true;
    };
  }, [sourceId, token, expireSession, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading", passage: null });
    setAttempt((n) => n + 1);
  }, []);

  return { ...state, retry };
}
