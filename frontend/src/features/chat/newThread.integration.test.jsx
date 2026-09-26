import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import ChatPage from "../../pages/ChatPage";
import * as chatService from "../../services/chatService";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/chatService");

// Real ChatPage and useMessages: the point is the handoff between them and
// the route change, which mocked hooks would hide.
describe("sending the first message in a new thread", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({
      token: "tok123",
      user: { email: "alice@example.com" },
      logout: vi.fn(),
      expireSession: vi.fn(),
    });
    chatService.listThreads.mockResolvedValue([]);
    chatService.listMessages.mockResolvedValue([]);
    chatService.createThread.mockResolvedValue({ id: "t2", title: null });
    chatService.streamMessage.mockImplementation(async (_t, _id, _c, { onEvent }) => {
      onEvent({ event: "user_message", data: { message: { id: "m1", role: "user", content: "What is a deductible?", created_at: "" } } });
      onEvent({
        event: "done",
        data: {
          message: { id: "m2", role: "assistant", content: "A deductible is what you pay first.", created_at: "", sources: [] },
          thread: { id: "t2", title: "What is a deductible?", updated_at: "" },
        },
      });
    });
  });

  it("survives the navigation from /chat to /chat/:threadId", async () => {
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:threadId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const composer = await screen.findByRole("textbox");
    await userEvent.type(composer, "What is a deductible?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(chatService.createThread).toHaveBeenCalled());
    // The pending message lives in a ref inside ChatPage. If the route change
    // remounts it, that ref resets and the message is silently dropped.
    await waitFor(() =>
      expect(chatService.streamMessage).toHaveBeenCalledWith("tok123", "t2", "What is a deductible?", expect.anything()),
    );
  });
});
