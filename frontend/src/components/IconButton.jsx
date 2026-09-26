// A button that shows only an icon, so its label is its accessible name.
export default function IconButton({ label, className = "", children, ...props }) {
  return (
    <button type="button" className={["iconbtn", className].filter(Boolean).join(" ")} aria-label={label} {...props}>
      {children}
    </button>
  );
}
