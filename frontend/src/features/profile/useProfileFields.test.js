import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../services/apiClient";
import { lookupCounties } from "../../services/profileService";
import { useProfileFields } from "./useProfileFields";

vi.mock("../../services/profileService");

const alpha = { county_fips: "48001", county_name: "Anderson", state: "TX" };
const beta = { county_fips: "48213", county_name: "Henderson", state: "TX" };

describe("useProfileFields", () => {
  // Braces matter: a function returned from beforeEach runs as its teardown.
  beforeEach(() => {
    lookupCounties.mockReset();
  });

  it("fills the county in for a ZIP code in only one", async () => {
    lookupCounties.mockResolvedValue({ counties: [alpha], marketplace_state: true });
    const { result } = renderHook(() => useProfileFields());

    act(() => result.current.setZipCode("75801"));

    await waitFor(() => expect(result.current.lookup.status).toBe("ready"));
    expect(result.current.payload.county_fips).toBe("48001");
  });

  it("requires a choice for a ZIP code spanning counties", async () => {
    lookupCounties.mockResolvedValue({ counties: [alpha, beta], marketplace_state: true });
    const { result } = renderHook(() => useProfileFields());

    act(() => {
      result.current.setZipCode("75751");
      result.current.setField("dateOfBirth", "1990-05-17");
    });
    await waitFor(() => expect(result.current.lookup.counties).toHaveLength(2));

    expect(result.current.validate()).toEqual({ county_fips: "Choose your county." });
  });

  it("ignores an answer for a ZIP code the user has since changed", async () => {
    let answerFirst;
    lookupCounties
      .mockReturnValueOnce(new Promise((resolve) => { answerFirst = resolve; }))
      .mockResolvedValueOnce({ counties: [beta], marketplace_state: true });
    const { result } = renderHook(() => useProfileFields());

    act(() => result.current.setZipCode("75801"));
    act(() => result.current.setZipCode("75751"));
    await waitFor(() => expect(result.current.lookup.status).toBe("ready"));
    await act(async () => answerFirst({ counties: [alpha], marketplace_state: true }));

    expect(result.current.lookup.counties).toEqual([beta]);
    expect(result.current.payload.county_fips).toBe("48213");
  });

  it("marks an unknown ZIP code as such", async () => {
    lookupCounties.mockRejectedValue(new ApiError("ZIP code not found", 404));
    const { result } = renderHook(() => useProfileFields());

    act(() => result.current.setZipCode("00404"));

    await waitFor(() => expect(result.current.lookup.status).toBe("not-found"));
    expect(result.current.validate().zip_code).toBe("We don't recognise this ZIP code.");
  });

  it("starts from a saved profile and its counties without looking them up again", () => {
    const saved = { zip_code: "75751", date_of_birth: "1990-05-17", county_fips: "48213" };
    const counties = { status: "ready", counties: [alpha, beta], marketplaceState: true };

    const { result } = renderHook(() => useProfileFields(saved, counties));

    expect(result.current.payload).toEqual({ zip_code: "75751", date_of_birth: "1990-05-17", county_fips: "48213" });
    expect(result.current.validate()).toEqual({});
    expect(lookupCounties).not.toHaveBeenCalled();
  });
});
