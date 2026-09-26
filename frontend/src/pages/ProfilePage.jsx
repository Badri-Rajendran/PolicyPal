import { ArrowLeft, Menu as MenuIcon, PanelLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import ErrorBanner from "../components/ErrorBanner";
import IconButton from "../components/IconButton";
import Toast from "../components/Toast";
import AppShell from "../features/chat/AppShell";
import Sidebar from "../features/chat/sidebar/Sidebar";
import { clearSourceCache } from "../features/chat/sources/useSource";
import { useSidebarHidden } from "../features/chat/useSidebarHidden";
import { useThreads } from "../features/chat/useThreads";
import ProfileForm from "../features/profile/ProfileForm";
import "../features/profile/profile.css";
import { useProfile } from "../features/profile/useProfile";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useShortcuts } from "../hooks/useShortcuts";
import { SessionExpiredError } from "../services/apiClient";

// The profile form inside the app shell, beside where its data goes (Profile.dc.html).
export default function ProfilePage() {
  const navigate = useNavigate();
  const phone = useMediaQuery("(max-width: 720px)");
  const { profile, counties, status, error, retry, save } = useProfile();
  const { threads, status: threadsStatus, removeThread, renameThread } = useThreads();
  const [sidebarHidden, setHidden] = useSidebarHidden();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toast, setToast] = useState("");

  const failed = (message) => (err) => {
    if (!(err instanceof SessionExpiredError)) setToast(message);
  };

  useShortcuts({
    onNewQuestion: () => navigate("/chat"),
    onEscape: () => setDrawerOpen(false),
  });

  const sidebar = (
    <Sidebar
      threads={threads}
      status={threadsStatus}
      selectedThreadId={null}
      onSelect={(id) => navigate(`/chat/${id}`)}
      onCreate={() => navigate("/chat")}
      onDelete={(id) => removeThread(id).catch(failed("Couldn't delete this thread. Try again."))}
      onRename={(id, title) => renameThread(id, title).catch(failed("Couldn't rename this thread. Try again."))}
      onHide={phone ? () => setDrawerOpen(false) : () => setHidden(true)}
      onSignOut={clearSourceCache}
    />
  );

  const main = (
    <main className="main">
      <header className={phone ? "topbar compact" : "topbar"}>
        {phone && (
          <IconButton label="Open your questions" onClick={() => setDrawerOpen(true)}>
            <MenuIcon className="i" aria-hidden="true" />
          </IconButton>
        )}
        {!phone && sidebarHidden && (
          <IconButton label="Show the sidebar" onClick={() => setHidden(false)}>
            <PanelLeft className="i" aria-hidden="true" />
          </IconButton>
        )}
        <Link to="/chat" className="back-link">
          <ArrowLeft className="i sm" aria-hidden="true" />
          Back to your questions
        </Link>
      </header>
      <div className="scroll">
        <div className="profile-layout">
          <div className="profile-main">
            <div className="profile-heading">
              <h1>Your profile</h1>
              <p className="muted">Plan questions use your ZIP code and age to find plans you can buy and price them for you.</p>
            </div>
            {status === "loading" && (
              <p className="muted" role="status">
                Loading your profile…
              </p>
            )}
            {status === "error" && (
              <div className="profile-error">
                <ErrorBanner>{error}</ErrorBanner>
                <button type="button" className="link" onClick={retry}>
                  Try again
                </button>
              </div>
            )}
            {status === "ready" && <ProfileForm profile={profile} counties={counties} onSave={save} />}
          </div>
          <aside className="profile-aside" aria-label="How this is used">
            <h2>Where this goes</h2>
            <p>What you save here stays on our server and is never sent to the AI model.</p>
            <p>Anything you type in a question is sent, so keep personal details out of questions.</p>
          </aside>
        </div>
      </div>
      <Toast message={toast} onDone={() => setToast("")} />
    </main>
  );

  return (
    <AppShell
      sidebar={sidebar}
      main={main}
      sidebarHidden={sidebarHidden}
      drawerOpen={drawerOpen}
      onCloseDrawer={() => setDrawerOpen(false)}
    />
  );
}
