import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { FOCUSABLE, trapTab } from "./focus";
import "./shell.css";

const SIDEBAR_WIDTH = 276;

// The phone's sidebar: a drawer over the chat, with focus moved into it, kept
// there, and returned when it closes.
function Drawer({ children, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    const opener = document.activeElement;
    ref.current?.querySelector(FOCUSABLE)?.focus();
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  return (
    <>
      <motion.div
        className="scrim"
        aria-hidden="true"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />
      <motion.div
        ref={ref}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Your questions"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation(); // not also the page's Esc
            onClose();
          } else {
            trapTab(event, ref.current);
          }
        }}
        initial={{ x: "-100%" }}
        animate={{ x: 0 }}
        exit={{ x: "-100%" }}
        transition={{ type: "tween", duration: 0.2 }}
      >
        {children}
      </motion.div>
    </>
  );
}

// Sidebar, main column and the Sources panel (Main.dc.html's .shell). The
// sidebar collapses on desktop and is a drawer at 720 px and below.
export default function AppShell({ sidebar, main, panel = null, sidebarHidden = false, drawerOpen = false, onCloseDrawer }) {
  const phone = useMediaQuery("(max-width: 720px)");
  const classes = ["shell", panel && !phone && "with-panel", sidebarHidden && !phone && "collapsed", phone && "phone"]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      {phone ? (
        <AnimatePresence>{drawerOpen && <Drawer onClose={onCloseDrawer}>{sidebar}</Drawer>}</AnimatePresence>
      ) : (
        <motion.div
          className="side-wrap"
          initial={false}
          animate={{ width: sidebarHidden ? 0 : SIDEBAR_WIDTH }}
          transition={{ duration: 0.2 }}
          inert={sidebarHidden}
          aria-hidden={sidebarHidden || undefined}
        >
          {sidebar}
        </motion.div>
      )}
      {/* Behind an open drawer the chat is hidden, as aria-modal says; the
          drawer keeps Tab. Not inert: that would blur the button that opened
          the drawer before the drawer could note it, and focus couldn't go back. */}
      <div className="shell-main" aria-hidden={(phone && drawerOpen) || undefined}>
        {main}
      </div>
      <AnimatePresence>{panel}</AnimatePresence>
    </div>
  );
}
