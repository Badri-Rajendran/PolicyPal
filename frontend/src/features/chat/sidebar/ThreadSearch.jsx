import { Search, X } from "lucide-react";
import { useRef } from "react";
import IconButton from "../../../components/IconButton";

// Filters the sidebar's thread titles as you type (SidebarSearch.dc.html).
export default function ThreadSearch({ value, onChange }) {
  const inputRef = useRef(null);

  return (
    <div className="search">
      <Search className="i sm" aria-hidden="true" />
      <input
        ref={inputRef}
        type="search"
        placeholder="Search your questions"
        aria-label="Search your questions"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {value && (
        <IconButton
          label="Clear search"
          className="search-clear"
          onClick={() => {
            onChange("");
            inputRef.current?.focus();
          }}
        >
          <X className="i sm" aria-hidden="true" />
        </IconButton>
      )}
    </div>
  );
}
