import { Link } from "react-router";
import ErrorBanner from "../components/ErrorBanner";
import ProfileForm from "../features/profile/ProfileForm";
import "../features/profile/profile.css";
import { useProfile } from "../features/profile/useProfile";

export default function ProfilePage() {
  const { profile, counties, status, error, retry, save } = useProfile();

  return (
    <div className="profile-screen">
      <main className="profile-card">
        <Link to="/chat" className="link">
          ← Back to your questions
        </Link>
        <h1>Your profile</h1>
        <p className="profile-intro">
          Plan questions use your ZIP code and age to find plans you can buy and price them for you. What you save
          here stays on our server and is never sent to the AI model; anything you type in a question is.
        </p>
        {status === "loading" && <p role="status">Loading your profile…</p>}
        {status === "error" && (
          <>
            <ErrorBanner>{error}</ErrorBanner>
            <button type="button" className="link" onClick={retry}>
              Try again
            </button>
          </>
        )}
        {status === "ready" && <ProfileForm profile={profile} counties={counties} onSave={save} />}
      </main>
    </div>
  );
}
