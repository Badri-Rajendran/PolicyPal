import { useState } from "react";
import Button from "../../components/Button";
import ErrorBanner from "../../components/ErrorBanner";
import TextField from "../../components/TextField";
import { useAuth } from "../../hooks/useAuth";
import { fieldErrorsFrom } from "../../utils/fieldErrors";
import ProfileFields from "../profile/ProfileFields";
import { useProfileFields } from "../profile/useProfileFields";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function AuthForm({ mode, onModeChange }) {
  const { login, register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const profile = useProfileFields();

  const isRegister = mode === "register";

  function validate() {
    const errors = {};
    if (!EMAIL_PATTERN.test(email)) errors.email = "Enter a valid email address.";
    if (isRegister && password.length < 8) errors.password = "Use at least 8 characters.";
    if (!isRegister && password.length === 0) errors.password = "Enter your password.";
    // Checked here first, so an under-13 date of birth is never even sent.
    if (isRegister) Object.assign(errors, profile.validate());
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError("");
    if (!validate()) return;

    setBusy(true);
    try {
      if (isRegister) {
        await register(email, password, profile.payload);
      } else {
        await login(email, password);
      }
    } catch (err) {
      const serverFieldErrors = fieldErrorsFrom(err);
      if (Object.keys(serverFieldErrors).length > 0) setFieldErrors(serverFieldErrors);
      else setFormError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <TextField
        id="email"
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldErrors.email}
      />
      <TextField
        id="password"
        label="Password"
        type="password"
        autoComplete={isRegister ? "new-password" : "current-password"}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={fieldErrors.password}
      />
      {isRegister && <ProfileFields fields={profile} errors={fieldErrors} />}
      <ErrorBanner>{formError}</ErrorBanner>
      <Button type="submit" busy={busy}>
        {isRegister ? "Create account" : "Sign in"}
      </Button>
      <p className="auth-switch">
        {isRegister ? "Already have an account?" : "New to PolicyPal?"}{" "}
        <button type="button" className="link" onClick={() => onModeChange(isRegister ? "login" : "register")}>
          {isRegister ? "Sign in" : "Create one"}
        </button>
      </p>
    </form>
  );
}
