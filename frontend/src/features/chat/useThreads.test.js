import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import { SessionExpiredError } from "../../services/apiClient";
import * as chatService from "../../services/chatService";
import { useThreads } from "./useThreads";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/chatService");

let expireSession;

beforeEach(() => {
  vi.clearAllMocks();
  expireSession = vi.fn();
  useAuth.mockReturnValue({ token: "tok123", expireSession });
});

describe("useThreads", () => {
  it("loads threads on mount", async () => {
    chatService.listThreads.mockResolvedValue([{ id: "t1", title: "Deductibles" }]);
    const { result } = renderHook(() => useThreads());

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.threads).toEqual([{ id: "t1", title: "Deductibles" }]);
  });

  it("surfaces a load error", async () => {
    chatService.listThreads.mockRejectedValue(new Error("network down"));
    const { result } = renderHook(() => useThreads());

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("network down");
  });

  it("creates a thread, prepending and selecting it", async () => {
    chatService.listThreads.mockResolvedValue([]);
    chatService.createThread.mockResolvedValue({ id: "t2", title: null });
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    await act(async () => {
      await result.current.createThread();
    });

    expect(result.current.threads[0].id).toBe("t2");
  });

  it("returns the created thread so the caller can navigate to it", async () => {
    chatService.listThreads.mockResolvedValue([]);
    chatService.createThread.mockResolvedValue({ id: "t2", title: null });
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    let created;
    await act(async () => {
      created = await result.current.createThread();
    });

    expect(created.id).toBe("t2");
  });

  it("removes a thread from the list", async () => {
    chatService.listThreads.mockResolvedValue([{ id: "t1", title: "Deductibles" }]);
    chatService.deleteThread.mockResolvedValue(null);
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    await act(async () => {
      await result.current.removeThread("t1");
    });

    expect(result.current.threads).toEqual([]);
  });

  it("moves a titled thread to the top of the list", async () => {
    chatService.listThreads.mockResolvedValue([
      { id: "t1", title: "Deductibles" },
      { id: "t2", title: null },
    ]);
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    act(() => result.current.touchThread("t2", "Auto claims process"));

    expect(result.current.threads[0]).toEqual({ id: "t2", title: "Auto claims process" });
  });

  it("records a thread's new activity time when it is touched", async () => {
    chatService.listThreads.mockResolvedValue([
      { id: "t1", title: "Deductibles", updated_at: "2026-09-01T00:00:00Z" },
      { id: "t2", title: "Copays", updated_at: "2026-08-01T00:00:00Z" },
    ]);
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    act(() => result.current.touchThread("t2", null, "2026-09-26T12:00:00Z"));

    expect(result.current.threads[0]).toEqual({ id: "t2", title: "Copays", updated_at: "2026-09-26T12:00:00Z" });
  });

  it("renames a thread at once, keeping the server's copy", async () => {
    chatService.listThreads.mockResolvedValue([{ id: "t1", title: "Deductibles" }]);
    let resolve;
    chatService.renameThread.mockReturnValue(new Promise((r) => (resolve = r)));
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    let pending;
    act(() => {
      pending = result.current.renameThread("t1", "What a deductible covers");
    });
    expect(result.current.threads[0].title).toBe("What a deductible covers");
    expect(chatService.renameThread).toHaveBeenCalledWith("tok123", "t1", "What a deductible covers");

    await act(async () => {
      resolve({ id: "t1", title: "What a deductible covers", updated_at: "x" });
      await pending;
    });
    expect(result.current.threads[0]).toEqual({ id: "t1", title: "What a deductible covers", updated_at: "x" });
  });

  it("restores the old title and rethrows when a rename fails", async () => {
    chatService.listThreads.mockResolvedValue([{ id: "t1", title: "Deductibles" }]);
    chatService.renameThread.mockRejectedValue(new Error("validation failed"));
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    let error;
    await act(async () => {
      error = await result.current.renameThread("t1", "New").catch((e) => e);
    });

    expect(error.message).toBe("validation failed");
    expect(result.current.threads[0].title).toBe("Deductibles");
  });

  it("expires the session when a rename's token is dead", async () => {
    chatService.listThreads.mockResolvedValue([{ id: "t1", title: "Deductibles" }]);
    chatService.renameThread.mockRejectedValue(new SessionExpiredError());
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    await act(async () => {
      await result.current.renameThread("t1", "New").catch(() => {});
    });

    expect(expireSession).toHaveBeenCalled();
  });

  it("retries after an error", async () => {
    chatService.listThreads.mockRejectedValueOnce(new Error("network down"));
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("error"));

    chatService.listThreads.mockResolvedValueOnce([{ id: "t1", title: "Deductibles" }]);
    act(() => result.current.retry());

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.threads).toHaveLength(1);
  });

  it("signs out instead of showing an error when the token has expired", async () => {
    chatService.listThreads.mockRejectedValue(new SessionExpiredError());
    const { result } = renderHook(() => useThreads());

    await waitFor(() => expect(expireSession).toHaveBeenCalled());
    // The user goes back to sign-in; an error banner here would be noise.
    expect(result.current.status).not.toBe("error");
  });
});
