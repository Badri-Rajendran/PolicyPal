import { Link } from "react-router";

export default function ProfileNudge() {
  return (
    <p className="profile-nudge">
      To compare health plans you can buy, add your ZIP code and date of birth to{" "}
      <Link to="/profile">your profile</Link>.
    </p>
  );
}
