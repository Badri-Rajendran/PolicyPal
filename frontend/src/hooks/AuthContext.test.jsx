import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as authService from "../services/authService";
import { AuthProvider } from "./AuthContext.jsx";
import { useAuth } from "./useAuth";

vi.mock("../services/authService");

function wrapper({ children }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("useAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("throws when used outside an AuthProvider", () => {
    expect(() => renderHook(() => useAuth())).toThrow("useAuth must be used within an AuthProvider");
  });

  it("starts signed out", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.status).toBe("signed-out");
  });

  it("becomes signed in after a successful login", async () => {
    authService.login.mockResolvedValue({ access_token: "tok123", user: { id: "u1", email: "alice@example.com" } });
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login("alice@example.com", "correct-horse-1");
    });

    expect(result.current.status).toBe("signed-in");
    expect(result.current.token).toBe("tok123");
    expect(result.current.user.email).toBe("alice@example.com");
  });

  it("becomes signed in after a successful registration", async () => {
    authService.register.mockResolvedValue({ access_token: "tok456", user: { id: "u2", email: "bob@example.com" } });
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.register("bob@example.com", "correct-horse-1");
    });

    expect(result.current.status).toBe("signed-in");
    expect(result.current.token).toBe("tok456");
  });

  it("propagates a login failure without changing state", async () => {
    authService.login.mockRejectedValue(new Error("invalid email or password"));
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(act(async () => result.current.login("alice@example.com", "wrong"))).rejects.toThrow(
      "invalid email or password",
    );
    expect(result.current.status).toBe("signed-out");
  });

  it("returns to signed out on logout", async () => {
    authService.login.mockResolvedValue({ access_token: "tok123", user: { id: "u1", email: "alice@example.com" } });
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login("alice@example.com", "correct-horse-1");
    });
    act(() => {
      result.current.logout();
    });

    expect(result.current.status).toBe("signed-out");
    expect(result.current.token).toBeNull();
  });

  it("restores the session on a reload", async () => {
    authService.login.mockResolvedValue({ access_token: "tok123", user: { id: "u1", email: "alice@example.com" } });
    const first = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await first.result.current.login("alice@example.com", "correct-horse-1");
    });
    first.unmount();

    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.status).toBe("signed-in");
    expect(result.current.token).toBe("tok123");
    expect(result.current.user.email).toBe("alice@example.com");
  });

  it("does not restore a session after logout", async () => {
    authService.login.mockResolvedValue({ access_token: "tok123", user: { id: "u1", email: "alice@example.com" } });
    const first = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await first.result.current.login("alice@example.com", "correct-horse-1");
    });
    act(() => first.result.current.logout());
    first.unmount();

    expect(renderHook(() => useAuth(), { wrapper }).result.current.status).toBe("signed-out");
  });

  it("reports an expired session separately from a deliberate sign out", async () => {
    authService.login.mockResolvedValue({ access_token: "tok123", user: { id: "u1", email: "alice@example.com" } });
    const { result, unmount } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login("alice@example.com", "correct-horse-1");
    });
    act(() => result.current.expireSession());

    expect(result.current.status).toBe("expired");
    expect(result.current.token).toBeNull();

    unmount();
    expect(renderHook(() => useAuth(), { wrapper }).result.current.status).toBe("signed-out");
  });

  it("survives unreadable storage", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });

    expect(renderHook(() => useAuth(), { wrapper }).result.current.status).toBe("signed-out");

    getItem.mockRestore();
  });
});
