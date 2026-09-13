import { useNavigate } from "react-router";
import AuthForm from "../features/auth/AuthForm";
import { useAuth } from "../hooks/useAuth";
import "../features/auth/auth.css";

export default function AuthPage({ mode = "login" }) {
  const { status } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <h1>PolicyPal</h1>
        </div>
        <p className="auth-tagline">Ask about your policy. Get answers with sources, not guesses.</p>
        {status === "expired" && (
          <p className="auth-notice" role="status">
            Your session has expired. Sign in again to pick up where you left off.
          </p>
        )}
        <AuthForm mode={mode} onModeChange={(next) => navigate(`/${next}`)} />
      </div>
    </div>
  );
}
