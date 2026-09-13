import { useCallback, useState } from "react";
import * as authService from "../services/authService";
import { AuthContext } from "./authContext.js";

export function AuthProvider({ children }) {
  const [session, setSession] = useState({ status: "signed-out", token: null, user: null });

  const login = useCallback(async (email, password) => {
    const data = await authService.login(email, password);
    setSession({ status: "signed-in", token: data.access_token, user: data.user });
  }, []);

  const register = useCallback(async (email, password) => {
    const data = await authService.register(email, password);
    setSession({ status: "signed-in", token: data.access_token, user: data.user });
  }, []);

  const logout = useCallback(() => {
    setSession({ status: "signed-out", token: null, user: null });
  }, []);

  return <AuthContext value={{ ...session, login, register, logout }}>{children}</AuthContext>;
}
