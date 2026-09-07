import { useState } from "react";
import AuthForm from "../features/auth/AuthForm";
import "../features/auth/auth.css";

export default function AuthPage() {
  const [mode, setMode] = useState("login");

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <h1>PolicyPal</h1>
        </div>
        <p className="auth-tagline">Ask about your policy. Get answers with sources, not guesses.</p>
        <AuthForm mode={mode} onModeChange={setMode} />
      </div>
    </div>
  );
}
