import { X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef } from "react";
import IconButton from "../../../components/IconButton";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { sourceNumbers } from "../../../utils/markers";
import { trapTab } from "../focus";
import SourceCard from "./SourceCard";
import "./sources.css";

// The cited passages of one answer (Main.dc.html's panel): a column beside the
// transcript, or a bottom sheet with a scrim at 720 px and below (Mobile.dc.html).
export default function SourcesPanel({ message, selectedSourceId, hoveredSourceId, onSelect, onClose }) {
  const phone = useMediaQuery("(max-width: 720px)");
  const containerRef = useRef(null);
  const closeRef = useRef(null);
  const cardRefs = useRef(new Map());
  const sources = message?.sources ?? [];
  const numbers = sourceNumbers(sources);

  // Focus is the DOM's: into the panel when it opens, back where it was when it closes.
  useEffect(() => {
    const opener = document.activeElement;
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  // The selected card is brought into view, and on opening it takes focus.
  const opened = useRef(false);
  useEffect(() => {
    const card = cardRefs.current.get(selectedSourceId);
    if (!opened.current) {
      opened.current = true;
      (card ?? closeRef.current)?.focus({ preventScroll: true });
    }
    card?.scrollIntoView({ block: "nearest" });
  }, [selectedSourceId]);

  function onKeyDown(event) {
    if (event.key === "Escape") {
      // Stopped here, so the page's Esc shortcut doesn't also run.
      event.preventDefault();
      event.stopPropagation();
      onClose();
    } else if (phone) {
      trapTab(event, containerRef.current);
    }
  }

  const cards = sources.map((source) => (
    <SourceCard
      key={source.id}
      source={source}
      number={numbers.get(source.source)}
      selected={source.id === selectedSourceId}
      hovered={source.id === hoveredSourceId}
      onSelect={onSelect}
      cardRef={(node) => {
        if (node) cardRefs.current.set(source.id, node);
        else cardRefs.current.delete(source.id);
      }}
    />
  ));

  const head = (
    <div className="panel-head">
      <h2>Sources</h2>
      <IconButton ref={closeRef} label="Close sources" onClick={onClose}>
        <X className="i" aria-hidden="true" />
      </IconButton>
    </div>
  );

  if (phone) {
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
        <motion.section
          ref={containerRef}
          className="sheet"
          role="dialog"
          aria-modal="true"
          aria-label="Sources"
          onKeyDown={onKeyDown}
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "tween", duration: 0.22 }}
        >
          <div className="grab" aria-hidden="true" />
          {head}
          <div className="sheet-body">{cards}</div>
        </motion.section>
      </>
    );
  }

  return (
    <motion.aside
      ref={containerRef}
      className="panel"
      aria-label="Sources"
      onKeyDown={onKeyDown}
      initial={{ x: 24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 24, opacity: 0 }}
      transition={{ duration: 0.18 }}
    >
      {head}
      <div className="panel-body">
        <p className="muted panel-intro">What the latest answer quotes. Select a numbered seal in the answer to jump here.</p>
        {cards}
        <p className="muted panel-foot">Quotes are short extracts. The carrier's PDF is the full document.</p>
      </div>
    </motion.aside>
  );
}
