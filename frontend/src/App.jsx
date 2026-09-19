import { Navigate, Route, Routes } from "react-router";
import { useAuth } from "./hooks/useAuth";
import AuthPage from "./pages/AuthPage";
import ChatPage from "./pages/ChatPage";
import ProfilePage from "./pages/ProfilePage";

function RequireAuth({ children }) {
  const { status } = useAuth();
  return status === "signed-in" ? children : <Navigate to="/login" replace />;
}

function RedirectWhenSignedIn({ children }) {
  const { status } = useAuth();
  return status === "signed-in" ? <Navigate to="/chat" replace /> : children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<RedirectWhenSignedIn><AuthPage mode="login" /></RedirectWhenSignedIn>} />
      <Route
        path="/register"
        element={<RedirectWhenSignedIn><AuthPage mode="register" /></RedirectWhenSignedIn>}
      />
      <Route path="/chat" element={<RequireAuth><ChatPage /></RequireAuth>} />
      <Route path="/chat/:threadId" element={<RequireAuth><ChatPage /></RequireAuth>} />
      <Route path="/profile" element={<RequireAuth><ProfilePage /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
