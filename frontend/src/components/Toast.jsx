import { motion } from "motion/react";
import { useEffect, useEffectEvent } from "react";

// A short-lived message that dismisses itself after `duration` ms.
export default function Toast({ message, onDone, duration = 2400, icon: Icon }) {
  const done = useEffectEvent(() => onDone?.());

  // The timer is outside React; a new message starts it again.
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(done, duration);
    return () => clearTimeout(timer);
  }, [message, duration]);

  if (!message) return null;
  return (
    <motion.div
      className="toast"
      role="status"
      initial={{ opacity: 0, x: "-50%", y: 8 }}
      animate={{ opacity: 1, x: "-50%", y: 0 }}
      transition={{ duration: 0.16 }}
    >
      {Icon && <Icon className="i" aria-hidden="true" />}
      {message}
    </motion.div>
  );
}
