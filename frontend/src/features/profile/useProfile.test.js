import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import { SessionExpiredError } from "../../services/apiClient";
import * as profileService from "../../services/profileService";
import { useProfile } from "./useProfile";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/profileService");

const saved = { zip_code: "75801", date_of_birth: "1990-05-17", county_fips: "48001" };
const found = { counties: [{ county_fips: "48001", county_name: "Anderson", state: "TX" }], marketplace_state: true };

describe("useProfile", () => {
  const expireSession = vi.fn();
  const updateUser = vi.fn();

  beforeEach(() => {
    vi.resetAllMocks();
    useAuth.mockReturnValue({ token: "tok", expireSession, updateUser });
  });

  it("loads the profile with its ZIP code's counties", async () => {
    profileService.getProfile.mockResolvedValue(saved);
    profileService.lookupCounties.mockResolvedValue(found);

    const { result } = renderHook(() => useProfile());

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.profile).toEqual(saved);
    expect(result.current.counties.counties).toEqual(found.counties);
  });

  it("still opens the profile when the county lookup fails", async () => {
    profileService.getProfile.mockResolvedValue(saved);
    profileService.lookupCounties.mockRejectedValue(new Error("down"));

    const { result } = renderHook(() => useProfile());

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.counties).toBeUndefined();
  });

  it("marks the session complete once a profile is saved", async () => {
    profileService.getProfile.mockResolvedValue({ zip_code: null });
    profileService.updateProfile.mockResolvedValue(saved);
    const { result } = renderHook(() => useProfile());
    await waitFor(() => expect(result.current.status).toBe("ready"));

    await act(() => result.current.save(saved));

    expect(profileService.updateProfile).toHaveBeenCalledWith("tok", saved);
    expect(updateUser).toHaveBeenCalledWith({ profile_complete: true });
  });

  it("ends an expired session instead of showing an error", async () => {
    profileService.getProfile.mockRejectedValue(new SessionExpiredError());

    renderHook(() => useProfile());

    await waitFor(() => expect(expireSession).toHaveBeenCalled());
  });
});
