import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import * as chatService from "../../services/chatService";
import { useMessages } from "./useMessages";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/chatService");

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ token: "tok123" });
});

describe("useMessages", () => {
  it("stays idle with no thread selected", () => {
    const { result } = renderHook(() => useMessages(null, vi.fn()));
    expect(result.current.status).toBe("idle");
    expect(result.current.messages).toEqual([]);
  });

  it("loads messages for the given thread", async () => {
    chatService.listMessages.mockResolvedValue([{ id: "m1", role: "user", content: "Hi" }]);
    const { result } = renderHook(() => useMessages("t1", vi.fn()));

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.messages).toEqual([{ id: "m1", role: "user", content: "Hi" }]);
  });

  it("resets when switching to a different thread", async () => {
    chatService.listMessages.mockResolvedValueOnce([{ id: "m1", role: "user", content: "Hi" }]);
    const { result, rerender } = renderHook(({ threadId }) => useMessages(threadId, vi.fn()), {
      initialProps: { threadId: "t1" },
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    chatService.listMessages.mockResolvedValueOnce([]);
    rerender({ threadId: "t2" });

    expect(result.current.messages).toEqual([]);
    await waitFor(() => expect(result.current.status).toBe("ready"));
  });

  it("keeps an optimistic message even if the history fetch resolves empty afterwards", async () => {
    let resolveHistory;
    chatService.listMessages.mockReturnValue(new Promise((resolve) => (resolveHistory = resolve)));
    chatService.sendMessage.mockImplementation(() => new Promise(() => {})); // never resolves in this test

    const { result } = renderHook(() => useMessages("t1", vi.fn()));

    // Simulates the real race: the send's optimistic append happens while the
    // GET for this brand-new thread is still in flight.
    act(() => {
      result.current.send("What is a deductible?");
    });
    expect(result.current.messages).toHaveLength(1);

    await act(async () => {
      resolveHistory([]);
      await Promise.resolve();
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe("user");
  });

  it("appends the assistant reply and titles a first message", async () => {
    chatService.listMessages.mockResolvedValue([]);
    chatService.sendMessage.mockResolvedValue({
      message: { id: "m2", role: "assistant", content: "It's the amount you pay first." },
      sources: [{ source: "wiki_Health.txt", chunk_id: "c1", relevance: 0.9 }],
    });
    const onThreadTitled = vi.fn();
    const { result } = renderHook(() => useMessages("t1", onThreadTitled));
    await waitFor(() => expect(result.current.status).toBe("ready"));

    await act(async () => {
      await result.current.send("What is a deductible?");
    });

    expect(result.current.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(result.current.isSending).toBe(false);
    expect(onThreadTitled).toHaveBeenCalledWith("t1", "What is a deductible?");
  });

  it("rolls back the optimistic message and surfaces an error on failure", async () => {
    chatService.listMessages.mockResolvedValue([]);
    chatService.sendMessage.mockRejectedValue(new Error("You're sending requests too quickly."));
    const { result } = renderHook(() => useMessages("t1", vi.fn()));
    await waitFor(() => expect(result.current.status).toBe("ready"));

    await act(async () => {
      await result.current.send("What is a deductible?");
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.sendError).toBe("You're sending requests too quickly.");
  });
});
