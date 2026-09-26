import { MapPin } from "lucide-react";
import { Link } from "react-router";

// Shown to an account without a profile (Mobile.dc.html's nudge).
export default function ProfileNudge() {
  return (
    <div className="nudge">
      <MapPin className="i sm" aria-hidden="true" />
      <span>
        To compare plans you can buy, add your ZIP code and date of birth in <Link to="/profile">your profile</Link>.
      </span>
    </div>
  );
}
