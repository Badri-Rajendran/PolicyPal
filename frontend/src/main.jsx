import { MotionConfig } from "motion/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App.jsx";
import { AuthProvider } from "./hooks/AuthContext.jsx";
import { applyTheme, readTheme } from "./hooks/useTheme";
import "./index.css";
import "./components/components.css";

// Before the first paint, so a dark choice never flashes light.
applyTheme(readTheme());

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>,
);
