export default function Button({ variant = "primary", busy = false, children, disabled, ...props }) {
  return (
    <button className={`btn btn-${variant}`} disabled={disabled || busy} {...props}>
      {busy ? "Working…" : children}
    </button>
  );
}
