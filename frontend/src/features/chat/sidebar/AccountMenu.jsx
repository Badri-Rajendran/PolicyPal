import { ChevronsUpDown, LogOut, Moon, Sun, User } from "lucide-react";
import { useId } from "react";
import { Link } from "react-router";
import Menu, { MenuItem } from "../../../components/Menu";
import { useAuth } from "../../../hooks/useAuth";
import { useTheme } from "../../../hooks/useTheme";
import { modKey } from "../../../utils/shortcutKey";

const THEMES = [
  { value: "system", label: "System" },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

// The sidebar's footer: profile, theme, shortcuts and sign out
// (SidebarAccount.dc.html).
export default function AccountMenu({ onSignOut }) {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const email = user?.email ?? "";
  const themeLabel = useId();

  return (
    <Menu
      label="Account"
      placement="above"
      className="account-anchor"
      trigger={(props) => (
        <button type="button" className="account" aria-label={`Account menu for ${email}`} {...props}>
          <span className="avatar" aria-hidden="true">
            {email.charAt(0).toUpperCase()}
          </span>
          <span className="account-email">{email}</span>
          <ChevronsUpDown className="i sm" aria-hidden="true" />
        </button>
      )}
    >
      <div className="menu-note muted">Signed in as {email}</div>
      <Link to="/profile" role="menuitem" tabIndex={-1} className="menu-link">
        <User className="i sm" aria-hidden="true" />
        Profile, ZIP code and date of birth
      </Link>
      <div className="menu-note muted" id={themeLabel}>
        Theme
      </div>
      <div role="radiogroup" aria-labelledby={themeLabel} className="theme-choice">
        {THEMES.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            role="radio"
            tabIndex={-1}
            aria-checked={theme === value}
            onClick={() => setTheme(value)}
          >
            {Icon && <Icon className="i sm" aria-hidden="true" />}
            {label}
          </button>
        ))}
      </div>
      <div className="menu-note muted">Shortcuts: {modKey()} K new question, / type a question, Esc close panels</div>
      <hr />
      <MenuItem
        icon={LogOut}
        onSelect={() => {
          onSignOut?.();
          logout();
        }}
      >
        Sign out
      </MenuItem>
    </Menu>
  );
}
