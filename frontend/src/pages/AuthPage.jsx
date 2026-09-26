import { useNavigate } from "react-router";
import AuthForm from "../features/auth/AuthForm";
import ExampleAnswer from "../features/auth/ExampleAnswer";
import { useAuth } from "../hooks/useAuth";
import "../features/auth/auth.css";
import "../features/profile/profile.css";

const HEADINGS = {
  login: { title: "Sign in", lede: "Pick up your questions where you left them." },
  register: {
    title: "Create an account",
    lede: "Your ZIP code and date of birth let plan questions find plans you can buy, priced for you.",
  },
};

// Sign in and register, beside an example cited answer (SignIn.dc.html).
export default function AuthPage({ mode = "login" }) {
  const { status } = useAuth();
  const navigate = useNavigate();
  const { title, lede } = HEADINGS[mode] ?? HEADINGS.login;

  return (
    <div className="auth-screen">
      <section className="auth-intro">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            P
          </span>
          <span className="brand-name">PolicyPal</span>
        </div>
        <h1>Answers about your health coverage, with the source for every claim.</h1>
        <ExampleAnswer />
      </section>
      <main className="auth-main">
        <div className="auth-panel">
          <div className="auth-heading">
            <h2>{title}</h2>
            <p className="muted">{lede}</p>
          </div>
          {status === "expired" && (
            <p className="auth-notice" role="status">
              Your session has expired. Sign in again to pick up where you left off.
            </p>
          )}
          <AuthForm mode={mode} onModeChange={(next) => navigate(`/${next}`)} />
        </div>
      </main>
    </div>
  );
}
