import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../services/apiClient";
import ProfileForm from "./ProfileForm";

vi.mock("../../services/profileService");

const saved = { zip_code: "75801", date_of_birth: "1990-05-17", county_fips: "48001" };
const counties = {
  status: "ready",
  counties: [{ county_fips: "48001", county_name: "Anderson", state: "TX" }],
  marketplaceState: true,
};

describe("ProfileForm", () => {
  const onSave = vi.fn();

  beforeEach(() => {
    onSave.mockReset().mockResolvedValue(saved);
  });

  it("opens with the saved profile", () => {
    render(<ProfileForm profile={saved} counties={counties} onSave={onSave} />);

    expect(screen.getByLabelText("ZIP code")).toHaveValue("75801");
    expect(screen.getByLabelText("Date of birth")).toHaveValue("1990-05-17");
    expect(screen.getByText("Anderson County, TX")).toBeInTheDocument();
  });

  it("saves and says so", async () => {
    render(<ProfileForm profile={saved} counties={counties} onSave={onSave} />);

    fireEvent.change(screen.getByLabelText("Date of birth"), { target: { value: "1985-01-02" } });
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));

    expect(onSave).toHaveBeenCalledWith({ zip_code: "75801", date_of_birth: "1985-01-02", county_fips: "48001" });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
  });

  it("refuses a date of birth under 13 without sending it", async () => {
    render(<ProfileForm profile={saved} counties={counties} onSave={onSave} />);

    fireEvent.change(screen.getByLabelText("Date of birth"), { target: { value: `${new Date().getFullYear() - 5}-01-01` } });
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));

    expect(screen.getByText("You must be at least 13 to use PolicyPal.")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("shows a field the server rejected beside it, and anything else above the button", async () => {
    onSave
      .mockRejectedValueOnce(new ApiError("validation failed", 422, [{ field: "zip_code", message: "We don't recognise this ZIP code." }]))
      .mockRejectedValueOnce(new ApiError("Can't reach PolicyPal right now.", 0));
    render(<ProfileForm profile={saved} counties={counties} onSave={onSave} />);

    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("We don't recognise this ZIP code.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach PolicyPal right now.");
  });
});
