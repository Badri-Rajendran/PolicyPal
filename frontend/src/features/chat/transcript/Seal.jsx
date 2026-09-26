import { motion } from "motion/react";

// A citation: a numbered brass seal that opens its source. When an answer
// has just finished streaming its seals stamp in, one after another; that is
// the app's one self-running animation (spec §4.3).
export default function Seal({ number, index = 0, stamp = false, selected = false, onClick, onHover }) {
  const button = (
    <button
      type="button"
      className={selected ? "seal sel" : "seal"}
      aria-label={`Source ${number}`}
      onClick={onClick}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      onFocus={() => onHover?.(true)}
      onBlur={() => onHover?.(false)}
    >
      {number}
    </button>
  );

  if (!stamp) return button;
  return (
    <motion.span
      className="stamp"
      initial={{ scale: 1.9, rotate: -14, opacity: 0 }}
      animate={{ scale: 1, rotate: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 18, delay: index * 0.08 }}
    >
      {button}
    </motion.span>
  );
}
