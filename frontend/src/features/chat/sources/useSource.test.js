import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../../hooks/useAuth";
import { SessionExpiredError } from "../../../services/apiClient";
import * as chatService from "../../../services/chatService";
import { clearSourceCache, useSource } from "./useSource";

vi.mock("../../../hooks/useAuth");
vi.mock("../../../services/chatService");

const passage = { id: "s1", kind: "wikipedia", title: "Health insurance", quote: "…", status: "ok" };
let expireSession;

beforeEach(() => {
  vi.clearAllMocks();
  clearSourceCache();
  expireSession = vi.fn();
  useAuth.mockReturnValue({ token: "tok", expireSession });
});

describe("useSource", () => {
  it("loads a passage", async () => {
    chatService.getSource.mockResolvedValue(passage);
    const { result } = renderHook(() => useSource("s1"));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.passage).toEqual(passage);
    expect(chatService.getSource).toHaveBeenCalledWith("tok", "s1");
  });

  it("fetches once per id: a second hook, at once or later, reuses it", async () => {
    chatService.getSource.mockResolvedValue(passage);
    const first = renderHook(() => useSource("s1"));
    const second = renderHook(() => useSource("s1"));
    await waitFor(() => expect(second.result.current.status).toBe("ready"));
    await waitFor(() => expect(first.result.current.status).toBe("ready"));

    const third = renderHook(() => useSource("s1"));
    expect(third.result.current).toMatchObject({ status: "ready", passage });
    expect(chatService.getSource).toHaveBeenCalledOnce();
  });

  it("forgets everything when the cache is cleared", async () => {
    chatService.getSource.mockResolvedValue(passage);
    const first = renderHook(() => useSource("s1"));
    await waitFor(() => expect(first.result.current.status).toBe("ready"));
    clearSourceCache();
    const second = renderHook(() => useSource("s1"));
    expect(second.result.current.status).toBe("loading");
    await waitFor(() => expect(second.result.current.status).toBe("ready"));
    expect(chatService.getSource).toHaveBeenCalledTimes(2);
  });

  it("reports an error, and retry fetches again", async () => {
    chatService.getSource.mockRejectedValueOnce(new Error("Something went wrong."));
    const { result } = renderHook(() => useSource("s1"));
    await waitFor(() => expect(result.current.status).toBe("error"));

    chatService.getSource.mockResolvedValueOnce(passage);
    act(() => result.current.retry());
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(chatService.getSource).toHaveBeenCalledTimes(2);
  });

  it("follows a change of id", async () => {
    chatService.getSource.mockImplementation(async (_t, id) => ({ ...passage, id }));
    const { result, rerender } = renderHook(({ id }) => useSource(id), { initialProps: { id: "s1" } });
    await waitFor(() => expect(result.current.passage?.id).toBe("s1"));
    rerender({ id: "s2" });
    await waitFor(() => expect(result.current.passage?.id).toBe("s2"));
  });

  it("expires the session on a dead token", async () => {
    chatService.getSource.mockRejectedValue(new SessionExpiredError());
    renderHook(() => useSource("s1"));
    await waitFor(() => expect(expireSession).toHaveBeenCalled());
  });
});
