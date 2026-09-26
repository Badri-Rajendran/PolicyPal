const VARIANTS = { primary: "", ghost: "ghost", danger: "danger" };

export default function Button({ variant = "primary", busy = false, className = "", children, disabled, ...props }) {
  const classes = ["btn", VARIANTS[variant], className].filter(Boolean).join(" ");
  return (
    <button className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...props}>
      {busy ? (
        <>
          <span className="spinner" aria-hidden="true" />
          <span className="visually-hidden">Working…</span>
        </>
      ) : (
        children
      )}
    </button>
  );
}
