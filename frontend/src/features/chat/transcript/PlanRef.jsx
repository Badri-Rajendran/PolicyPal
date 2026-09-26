const FLASH_MS = 1400;

// A plan named in an answer: its number in the answer's table, then its name.
// Selecting it scrolls to that row and flashes it.
export default function PlanRef({ position, messageId, name, children }) {
  function show() {
    const row = document.getElementById(`plan-${messageId}-${position}`);
    if (!row) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    row.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
    // The flash is the DOM's for a moment; React never sets the row's class.
    row.classList.add("flash");
    setTimeout(() => row.classList.remove("flash"), FLASH_MS);
  }

  return (
    <button type="button" className="planref" aria-label={`Plan ${position}, ${name}`} onClick={show}>
      <span className="num" aria-hidden="true">
        {position}
      </span>
      {children}
    </button>
  );
}
