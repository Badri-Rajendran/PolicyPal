import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import * as chatService from "../../services/chatService";
import { useThreads } from "./useThreads";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/chatService");

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ token: "tok123" });
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
    expect(result.current.selectedThreadId).toBe("t2");
  });

  it("removes a thread and clears selection if it was selected", async () => {
    chatService.listThreads.mockResolvedValue([{ id: "t1", title: "Deductibles" }]);
    chatService.deleteThread.mockResolvedValue(null);
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    act(() => result.current.selectThread("t1"));
    await act(async () => {
      await result.current.removeThread("t1");
    });

    expect(result.current.threads).toEqual([]);
    expect(result.current.selectedThreadId).toBeNull();
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

  it("retries after an error", async () => {
    chatService.listThreads.mockRejectedValueOnce(new Error("network down"));
    const { result } = renderHook(() => useThreads());
    await waitFor(() => expect(result.current.status).toBe("error"));

    chatService.listThreads.mockResolvedValueOnce([{ id: "t1", title: "Deductibles" }]);
    act(() => result.current.retry());

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.threads).toHaveLength(1);
  });
});
