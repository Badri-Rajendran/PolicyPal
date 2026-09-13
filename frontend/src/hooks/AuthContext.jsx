import { useCallback, useState } from "react";
import * as authService from "../services/authService";
import { AuthContext } from "./authContext.js";

const STORAGE_KEY = "policypal.session";

const SIGNED_OUT = { status: "signed-out", token: null, user: null };
// A session the server rejected, so the sign-in screen can say why.
const EXPIRED = { status: "expired", token: null, user: null };

// sessionStorage rather than localStorage: a reload keeps you signed in, but
// the token dies with the tab instead of sitting on disk until it expires.
function readStoredSession() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY));
    if (!stored?.token || !stored?.user) return SIGNED_OUT;
    return { status: "signed-in", token: stored.token, user: stored.user };
  } catch {
    return SIGNED_OUT;
  }
}

function store(session) {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: session.token, user: session.user }),
    );
  } catch {
    // Storage can be unavailable or full; the session still works for this tab.
  }
}

function clearStored() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing readable to clear.
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(readStoredSession);

  const signIn = useCallback((data) => {
    const next = { status: "signed-in", token: data.access_token, user: data.user };
    store(next);
    setSession(next);
  }, []);

  const login = useCallback(
    async (email, password) => signIn(await authService.login(email, password)),
    [signIn],
  );

  const register = useCallback(
    async (email, password) => signIn(await authService.register(email, password)),
    [signIn],
  );

  const logout = useCallback(() => {
    clearStored();
    setSession(SIGNED_OUT);
  }, []);

  const expireSession = useCallback(() => {
    clearStored();
    setSession(EXPIRED);
  }, []);

  return (
    <AuthContext value={{ ...session, login, register, logout, expireSession }}>
      {children}
    </AuthContext>
  );
}
