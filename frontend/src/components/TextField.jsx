import { CircleAlert, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import IconButton from "./IconButton";

export default function TextField({ id, label, error, hint, type = "text", ...inputProps }) {
  const [shown, setShown] = useState(false);
  const isPassword = type === "password";
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;

  const input = (
    <input
      id={id}
      type={isPassword && shown ? "text" : type}
      className={error ? "bad" : undefined}
      aria-invalid={Boolean(error)}
      aria-describedby={describedBy}
      {...inputProps}
    />
  );

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {isPassword ? (
        <div className="field-password">
          {input}
          <IconButton label={shown ? "Hide password" : "Show password"} aria-pressed={shown} onClick={() => setShown((s) => !s)}>
            {shown ? <EyeOff className="i" aria-hidden="true" /> : <Eye className="i" aria-hidden="true" />}
          </IconButton>
        </div>
      ) : (
        input
      )}
      {hint && (
        <span className="help" id={`${id}-hint`}>
          {hint}
        </span>
      )}
      {error && (
        <p className="field-error" id={`${id}-error`}>
          <CircleAlert className="i sm" aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
}
