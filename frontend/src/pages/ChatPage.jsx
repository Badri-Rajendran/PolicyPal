import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import ErrorBanner from "../components/ErrorBanner";
import Toast from "../components/Toast";
import AppShell from "../features/chat/AppShell";
import ChatHeader from "../features/chat/ChatHeader";
import Composer from "../features/chat/composer/Composer";
import ProfileNudge from "../features/chat/composer/ProfileNudge";
import Sidebar from "../features/chat/sidebar/Sidebar";
import SourcesPanel from "../features/chat/sources/SourcesPanel";
import { clearSourceCache } from "../features/chat/sources/useSource";
import Transcript from "../features/chat/transcript/Transcript";
import { useMessages } from "../features/chat/useMessages";
import { useThreads } from "../features/chat/useThreads";
import "../features/plans/plans.css";
import { useAuth } from "../hooks/useAuth";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useShortcuts } from "../hooks/useShortcuts";
import { SessionExpiredError } from "../services/apiClient";

const SIDEBAR_KEY = "policypal.sidebar";

// localStorage holds only whether the sidebar is hidden, per browser.
function readSidebarHidden() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "hidden";
  } catch {
    return false;
  }
}

function storeSidebarHidden(hidden) {
  try {
    if (hidden) localStorage.setItem(SIDEBAR_KEY, "hidden");
    else localStorage.removeItem(SIDEBAR_KEY);
  } catch {
    // Storage unavailable: the choice holds for this page only.
  }
}

function placeholderFor({ isSending, hasMessages, phone }) {
  if (isSending) return "PolicyPal is answering…";
  if (!hasMessages) return "Ask about a plan, a term, or your coverage";
  return phone ? "Ask a follow-up" : "Ask a follow-up, or about another plan";
}

export default function ChatPage() {
  const { threadId = null } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const phone = useMediaQuery("(max-width: 720px)");
  const { threads, status, error, createThread, removeThread, renameThread, touchThread, retry } = useThreads();
  const { messages, live, isSending, sendError, stoppedId, finishedId, send, stop, ...thread } = useMessages(
    threadId,
    (saved) => touchThread(saved.id, saved.title, saved.updated_at),
  );

  const [draft, setDraft] = useState("");
  const [shownThreadId, setShownThreadId] = useState(threadId);
  const [sidebarHidden, setSidebarHidden] = useState(readSidebarHidden);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The Sources panel: which answer's sources, and which one is selected.
  const [panel, setPanel] = useState(null);
  const [hoveredSourceId, setHoveredSourceId] = useState(null);
  const [toast, setToast] = useState("");
  const composerRef = useRef(null);
  // The first question on /chat waits here while its thread is created.
  const pendingFirstMessage = useRef(null);

  if (threadId !== shownThreadId) {
    setShownThreadId(threadId);
    setDraft("");
    setPanel(null);
    setDrawerOpen(false);
  }

  // Sends the waiting first question once the new thread's route is open.
  useEffect(() => {
    if (threadId && pendingFirstMessage.current) {
      const content = pendingFirstMessage.current;
      pendingFirstMessage.current = null;
      send(content);
    }
    // Runs once per new thread id, using whichever `send` closure this render created.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const selectedThread = threads.find((t) => t.id === threadId);
  const latestWithSources = messages.findLast((m) => m.role === "assistant" && m.sources?.length > 0);
  const panelMessage = panel ? messages.find((m) => m.id === panel.messageId) : null;

  async function startThread() {
    const created = await createThread();
    navigate(`/chat/${created.id}`);
    return created;
  }

  function newQuestion() {
    startThread().catch(() => setToast("Couldn't start a new question. Try again."));
  }

  async function submit(content) {
    setDraft("");
    if (!threadId) {
      pendingFirstMessage.current = content;
      try {
        await startThread();
      } catch {
        pendingFirstMessage.current = null;
        setDraft(content);
        setToast("Couldn't start a new question. Try again.");
      }
    } else {
      send(content);
    }
  }

  function deleteThread(id) {
    removeThread(id).then(
      () => {
        if (id === threadId) navigate("/chat", { replace: true });
      },
      (err) => {
        if (!(err instanceof SessionExpiredError)) setToast("Couldn't delete this thread. Try again.");
      },
    );
  }

  function rename(id, title) {
    renameThread(id, title).catch((err) => {
      if (!(err instanceof SessionExpiredError)) setToast("Couldn't rename this thread. Try again.");
    });
  }

  function setHidden(hidden) {
    storeSidebarHidden(hidden);
    setSidebarHidden(hidden);
  }

  function fillComposer(text) {
    setDraft(text);
    composerRef.current?.focus();
  }

  function toggleSources() {
    if (panel) setPanel(null);
    else if (latestWithSources) setPanel({ messageId: latestWithSources.id, sourceId: latestWithSources.sources[0].id });
  }

  useShortcuts({
    onNewQuestion: newQuestion,
    onFocusComposer: () => composerRef.current?.focus(),
    onEscape: () => {
      if (isSending) stop();
      else if (panel) setPanel(null);
      else if (drawerOpen) setDrawerOpen(false);
    },
  });

  if (status === "error") {
    return (
      <div className="shell-error">
        <ErrorBanner>{error}</ErrorBanner>
        <button type="button" className="link" onClick={retry}>
          Try again
        </button>
      </div>
    );
  }

  const sidebar = (
    <Sidebar
      threads={threads}
      status={status}
      selectedThreadId={threadId}
      onSelect={(id) => {
        setDrawerOpen(false);
        navigate(`/chat/${id}`);
      }}
      onDelete={deleteThread}
      onCreate={newQuestion}
      onRename={rename}
      onHide={phone ? () => setDrawerOpen(false) : () => setHidden(true)}
      onSignOut={clearSourceCache}
    />
  );

  const main = (
    <main className="main">
      <ChatHeader
        title={selectedThread?.title || "New question"}
        onRename={selectedThread ? (title) => rename(selectedThread.id, title) : undefined}
        sourcesCount={latestWithSources?.sources.length ?? 0}
        sourcesOpen={panel !== null}
        onToggleSources={toggleSources}
        sidebarHidden={sidebarHidden}
        onShowSidebar={() => setHidden(false)}
        compact={phone}
        onOpenDrawer={() => setDrawerOpen(true)}
        onNewQuestion={newQuestion}
      />
      {/* Strictly false: a session stored before profiles existed has no flag, and is not nagged on a guess. */}
      {user?.profile_complete === false && <ProfileNudge />}
      <Transcript
        messages={messages}
        status={thread.status}
        error={thread.error}
        live={live}
        stoppedId={stoppedId}
        finishedId={finishedId}
        selectedSourceId={panel?.sourceId ?? null}
        onPrompt={fillComposer}
        onRetry={thread.retry}
        onAskAgain={send}
        onOpenSource={(message, sourceId) => setPanel({ messageId: message.id, sourceId })}
        onHoverSource={setHoveredSourceId}
        onAskAboutPlan={(position, name) => fillComposer(`About plan ${position}, ${name}: `)}
      />
      <div className="dock">
        <ErrorBanner>{sendError}</ErrorBanner>
        <Composer
          ref={composerRef}
          value={draft}
          onChange={setDraft}
          onSubmit={submit}
          onStop={stop}
          isSending={isSending}
          placeholder={placeholderFor({ isSending, hasMessages: messages.length > 0, phone })}
        />
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
      panel={
        panelMessage && (
          <SourcesPanel
            key="sources"
            message={panelMessage}
            selectedSourceId={panel.sourceId}
            hoveredSourceId={hoveredSourceId}
            onSelect={(sourceId) => setPanel({ ...panel, sourceId })}
            onClose={() => setPanel(null)}
          />
        )
      }
    />
  );
}
