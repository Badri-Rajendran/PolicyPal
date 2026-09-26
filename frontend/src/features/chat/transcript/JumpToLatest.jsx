import { ArrowDown } from "lucide-react";
import { motion } from "motion/react";

// Shown when the reader is well above the latest answer.
export default function JumpToLatest({ onClick }) {
  return (
    <motion.button
      type="button"
      className="jump"
      onClick={onClick}
      initial={{ opacity: 0, x: "-50%", y: 6 }}
      animate={{ opacity: 1, x: "-50%", y: 0 }}
      transition={{ duration: 0.15 }}
    >
      <ArrowDown className="i sm" aria-hidden="true" />
      Jump to latest
    </motion.button>
  );
}
