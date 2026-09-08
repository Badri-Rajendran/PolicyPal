import { useAuth } from "./hooks/useAuth";
import AuthPage from "./pages/AuthPage";
import ChatPage from "./pages/ChatPage";

export default function App() {
  const { status } = useAuth();
  return status === "signed-in" ? <ChatPage /> : <AuthPage />;
}
