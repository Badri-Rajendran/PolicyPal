import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, apiStream } from "./apiClient";
import { getSource, renameThread, streamMessage } from "./chatService";

vi.mock("./apiClient", () => ({ apiFetch: vi.fn(), apiStream: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("chatService", () => {
  it("streams a message to the thread's stream route", () => {
    const signal = new AbortController().signal;
    const onEvent = vi.fn();
    streamMessage("tok", "t1", "Q", { signal, onEvent });
    expect(apiStream).toHaveBeenCalledWith("/api/chat/threads/t1/messages/stream", {
      token: "tok",
      body: { content: "Q" },
      signal,
      onEvent,
    });
  });

  it("renames a thread with PATCH", () => {
    renameThread("tok", "t1", "New");
    expect(apiFetch).toHaveBeenCalledWith("/api/chat/threads/t1", { method: "PATCH", token: "tok", body: { title: "New" } });
  });

  it("fetches a cited passage by its source id", () => {
    getSource("tok", "s1");
    expect(apiFetch).toHaveBeenCalledWith("/api/chat/sources/s1", { token: "tok" });
  });
});
