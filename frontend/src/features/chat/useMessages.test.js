import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import { ApiError, SessionExpiredError } from "../../services/apiClient";
import * as chatService from "../../services/chatService";
import { useMessages } from "./useMessages";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/chatService");

let expireSession;

beforeEach(() => {
  vi.clearAllMocks();
  expireSession = vi.fn();
  useAuth.mockReturnValue({ token: "tok123", expireSession });
});

// streamMessage resolves after handing each event to onEvent, as apiStream does.
function streamWith(events) {
  chatService.streamMessage.mockImplementation(async (_t, _id, _c, { onEvent }) => {
    for (const e of events) onEvent(e);
  });
}

// A stream left open: the test emits events, and aborting rejects it.
function openStream() {
  const stream = {};
  chatService.streamMessage.mockImplementation(
    (_t, _i, _c, { onEvent, signal }) =>
      new Promise((_resolve, reject) => {
        stream.emit = onEvent;
        stream.signal = signal;
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      }),
  );
  return stream;
}

const question = { id: "q1", role: "user", content: "Q" };

async function ready(threadId = "t1", onThreadUpdated = vi.fn()) {
  const hook = renderHook(() => useMessages(threadId, onThreadUpdated));
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  return hook;
}

describe("useMessages", () => {
  it("stays idle with no thread selected", () => {
    const { result } = renderHook(() => useMessages(null, vi.fn()));
    expect(result.current.status).toBe("idle");
    expect(result.current.messages).toEqual([]);
    expect(result.current.live).toBeNull();
    expect(result.current.isSending).toBe(false);
  });

  it("loads messages for the given thread", async () => {
    chatService.listMessages.mockResolvedValue([{ id: "m1", role: "user", content: "Hi" }]);
    const { result } = renderHook(() => useMessages("t1", vi.fn()));

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.messages).toEqual([{ id: "m1", role: "user", content: "Hi" }]);
    expect(result.current.finishedId).toBeNull();
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
    chatService.streamMessage.mockImplementation(() => new Promise(() => {})); // never resolves in this test

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

  it("streams stages, notices and text, then replaces the draft with done", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const onThreadUpdated = vi.fn();
    const saved = { id: "a1", role: "assistant", content: "Notice.\n\nAnswer.", sources: [], plans: [] };
    streamWith([
      { event: "user_message", data: { message: question } },
      { event: "stage", data: { stage: "searching" } },
      { event: "notice", data: { text: "Notice." } },
      { event: "delta", data: { text: "Ans" } },
      { event: "done", data: { message: saved, thread: { id: "t1", title: "Q" } } },
    ]);
    const { result } = await ready("t1", onThreadUpdated);

    await act(() => result.current.send("Q"));

    expect(chatService.streamMessage).toHaveBeenCalledWith("tok123", "t1", "Q", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(result.current.messages.map((m) => m.id)).toEqual(["q1", "a1"]);
    expect(result.current.live).toBeNull();
    expect(result.current.isSending).toBe(false);
    expect(result.current.finishedId).toBe("a1");
    expect(result.current.sendError).toBe("");
    expect(onThreadUpdated).toHaveBeenCalledWith({ id: "t1", title: "Q" });
  });

  it("shows the live draft while it streams", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const stream = openStream();
    const { result } = await ready();

    act(() => {
      result.current.send("Q");
    });
    expect(result.current.isSending).toBe(true);
    expect(result.current.live).toEqual({ questionId: expect.stringMatching(/^temp-/), stages: [], notices: [], text: "" });

    act(() => stream.emit({ event: "user_message", data: { message: question } }));
    act(() => stream.emit({ event: "stage", data: { stage: "searching" } }));
    act(() => stream.emit({ event: "notice", data: { text: "Plans in CA…" } }));
    act(() => stream.emit({ event: "delta", data: { text: "Let " } }));
    act(() => stream.emit({ event: "delta", data: { text: "me look" } }));

    expect(result.current.messages).toEqual([question]);
    expect(result.current.live).toEqual({ questionId: "q1", stages: ["searching"], notices: ["Plans in CA…"], text: "Let me look" });
  });

  it("reset clears the streamed text", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const stream = openStream();
    const { result } = await ready();
    act(() => {
      result.current.send("Q");
    });
    act(() => stream.emit({ event: "delta", data: { text: "Let me look" } }));
    expect(result.current.live.text).toBe("Let me look");
    act(() => stream.emit({ event: "reset", data: {} }));
    expect(result.current.live.text).toBe("");
  });

  it("forgets the finished answer when the thread changes, so reloaded history never stamps", async () => {
    chatService.listMessages.mockResolvedValue([]);
    streamWith([
      { event: "user_message", data: { message: question } },
      { event: "done", data: { message: { id: "a1", role: "assistant", content: "A", sources: [], plans: [] }, thread: { id: "t1" } } },
    ]);
    const { result, rerender } = renderHook(({ threadId }) => useMessages(threadId, vi.fn()), {
      initialProps: { threadId: "t1" },
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    await act(() => result.current.send("Q"));
    expect(result.current.finishedId).toBe("a1");

    rerender({ threadId: "t2" });
    rerender({ threadId: "t1" });
    expect(result.current.finishedId).toBeNull();
  });

  it("a repeated stage moves to the end", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const stream = openStream();
    const { result } = await ready();
    act(() => {
      result.current.send("Q");
    });
    act(() => stream.emit({ event: "stage", data: { stage: "writing" } }));
    act(() => stream.emit({ event: "stage", data: { stage: "plans" } }));
    act(() => stream.emit({ event: "stage", data: { stage: "writing" } }));
    expect(result.current.live.stages).toEqual(["plans", "writing"]);
  });

  it("an error event keeps the saved question and shows the send error", async () => {
    chatService.listMessages.mockResolvedValue([]);
    streamWith([
      { event: "user_message", data: { message: question } },
      { event: "delta", data: { text: "Half" } },
      { event: "error", data: { error: "generation failed" } },
    ]);
    const { result } = await ready();

    await act(() => result.current.send("Q"));

    expect(result.current.messages.map((m) => m.id)).toEqual(["q1"]);
    expect(result.current.sendError).toBe("PolicyPal couldn't write an answer just now. Try again.");
    expect(result.current.live).toBeNull();
  });

  it("a stream that ends without an answer says so", async () => {
    chatService.listMessages.mockResolvedValue([]);
    streamWith([{ event: "user_message", data: { message: question } }]);
    const { result } = await ready();

    await act(() => result.current.send("Q"));

    expect(result.current.messages.map((m) => m.id)).toEqual(["q1"]);
    expect(result.current.sendError).toBe("PolicyPal couldn't write an answer just now. Try again.");
  });

  it("a failure before the stream removes the optimistic question", async () => {
    chatService.listMessages.mockResolvedValue([]);
    chatService.streamMessage.mockRejectedValue(
      new ApiError("You're sending requests too quickly. Wait a moment and try again.", 429),
    );
    const { result } = await ready();

    await act(() => result.current.send("What is a deductible?"));

    expect(result.current.messages).toEqual([]);
    expect(result.current.sendError).toBe("You're sending requests too quickly. Wait a moment and try again.");
    expect(result.current.live).toBeNull();
  });

  it("a new send clears the last send error", async () => {
    chatService.listMessages.mockResolvedValue([]);
    chatService.streamMessage.mockRejectedValueOnce(new ApiError("Something went wrong.", 500));
    const { result } = await ready();
    await act(() => result.current.send("Q"));
    expect(result.current.sendError).toBe("Something went wrong.");

    openStream();
    act(() => {
      result.current.send("Q");
    });
    expect(result.current.sendError).toBe("");
  });

  it("stop aborts, keeps the question, and marks it stopped", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const stream = openStream();
    const { result } = await ready();
    let sending;
    act(() => {
      sending = result.current.send("Q");
    });
    act(() => stream.emit({ event: "user_message", data: { message: question } }));
    act(() => stream.emit({ event: "delta", data: { text: "Partial" } }));

    await act(async () => {
      result.current.stop();
      await sending;
    });

    expect(stream.signal.aborted).toBe(true);
    expect(result.current.live).toBeNull();
    expect(result.current.stoppedId).toBe("q1");
    expect(result.current.messages).toEqual([question]);
    expect(result.current.sendError).toBe("");
  });

  it("the next send clears the stopped mark", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const stream = openStream();
    const { result } = await ready();
    let sending;
    act(() => {
      sending = result.current.send("Q");
    });
    act(() => stream.emit({ event: "user_message", data: { message: question } }));
    await act(async () => {
      result.current.stop();
      await sending;
    });
    expect(result.current.stoppedId).toBe("q1");

    openStream();
    act(() => {
      result.current.send("Q again");
    });
    expect(result.current.stoppedId).toBeNull();
  });

  it("ignores a second send while an answer is live", async () => {
    chatService.listMessages.mockResolvedValue([]);
    openStream();
    const { result } = await ready();
    act(() => {
      result.current.send("Q");
    });
    act(() => {
      result.current.send("Q");
    });
    expect(chatService.streamMessage).toHaveBeenCalledOnce();
    expect(result.current.messages).toHaveLength(1);
  });

  it("aborts a live answer when the thread changes", async () => {
    chatService.listMessages.mockResolvedValue([]);
    const stream = openStream();
    const { result, rerender } = renderHook(({ threadId }) => useMessages(threadId, vi.fn()), {
      initialProps: { threadId: "t1" },
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    act(() => {
      result.current.send("Q");
    });

    await act(async () => {
      rerender({ threadId: "t2" });
    });

    expect(stream.signal.aborted).toBe(true);
    expect(result.current.live).toBeNull();
    expect(result.current.messages).toEqual([]);
  });

  it("an expired session calls expireSession", async () => {
    chatService.listMessages.mockResolvedValue([]);
    chatService.streamMessage.mockRejectedValue(new SessionExpiredError());
    const { result } = await ready();

    await act(() => result.current.send("Q"));

    expect(expireSession).toHaveBeenCalled();
    expect(result.current.sendError).toBe("");
  });

  it("reports a failed history load rather than looking empty", async () => {
    chatService.listMessages.mockRejectedValue(new Error("Something went wrong."));
    const { result } = renderHook(() => useMessages("t1", vi.fn()));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Something went wrong.");
    expect(result.current.messages).toEqual([]);
  });

  it("loads the thread again when retried", async () => {
    chatService.listMessages.mockRejectedValueOnce(new Error("Something went wrong."));
    const { result } = renderHook(() => useMessages("t1", vi.fn()));
    await waitFor(() => expect(result.current.status).toBe("error"));

    chatService.listMessages.mockResolvedValueOnce([{ id: "m1", role: "user", content: "Hi" }]);
    act(() => {
      result.current.retry();
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.error).toBe("");
    expect(result.current.messages).toHaveLength(1);
  });

  it("clears a previous failure when switching threads", async () => {
    chatService.listMessages.mockRejectedValueOnce(new Error("Something went wrong."));
    const { result, rerender } = renderHook(({ threadId }) => useMessages(threadId, vi.fn()), {
      initialProps: { threadId: "t1" },
    });
    await waitFor(() => expect(result.current.status).toBe("error"));

    chatService.listMessages.mockResolvedValueOnce([]);
    rerender({ threadId: "t2" });

    expect(result.current.error).toBe("");
    await waitFor(() => expect(result.current.status).toBe("ready"));
  });
});
