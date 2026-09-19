import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ProfileFields from "./ProfileFields";

const alpha = { county_fips: "48001", county_name: "Anderson", state: "TX" };
const beta = { county_fips: "48213", county_name: "Henderson", state: "TX" };

function renderFields(lookup, { errors = {}, values = {} } = {}) {
  const fields = {
    values: { zipCode: "75751", dateOfBirth: "", countyFips: "", ...values },
    lookup: { status: "ready", counties: [], marketplaceState: true, ...lookup },
    setZipCode: vi.fn(),
    setField: vi.fn(),
  };
  render(<ProfileFields fields={fields} errors={errors} />);
  return fields;
}

describe("ProfileFields", () => {
  it("labels every input", () => {
    renderFields({ counties: [alpha, beta] });

    expect(screen.getByLabelText("ZIP code")).toBeInTheDocument();
    expect(screen.getByLabelText("Date of birth")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("County")).toBeInTheDocument();
  });

  it("offers a county choice only when the ZIP code spans several", async () => {
    const fields = renderFields({ counties: [alpha, beta] });

    await userEvent.selectOptions(screen.getByLabelText("County"), "48213");

    expect(fields.setField).toHaveBeenCalledWith("countyFips", "48213");
  });

  it("names the one county instead of asking", () => {
    renderFields({ counties: [alpha] });

    expect(screen.queryByLabelText("County")).not.toBeInTheDocument();
    expect(screen.getByText("Anderson County, TX")).toBeInTheDocument();
  });

  it("says while the county is being looked up, and when the lookup failed", () => {
    renderFields({ status: "loading" });
    expect(screen.getByRole("status")).toHaveTextContent("Finding your county…");
  });

  it("lets signup continue when the lookup failed", () => {
    renderFields({ status: "error" });
    expect(screen.getByText(/Couldn't look up this ZIP code right now/)).toBeInTheDocument();
  });

  it("marks an unknown ZIP code on the field itself", () => {
    renderFields({ status: "not-found" });

    expect(screen.getByLabelText("ZIP code")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("We don't recognise this ZIP code.")).toBeInTheDocument();
  });

  it("explains a state with its own exchange without blocking signup", () => {
    renderFields({ counties: [{ county_fips: "17031", county_name: "Cook", state: "IL" }], marketplaceState: false });

    expect(screen.getByText(/runs its own health insurance exchange/)).toBeInTheDocument();
  });

  it("ties each error to its field", () => {
    renderFields({ counties: [alpha, beta] }, { errors: { date_of_birth: "You must be at least 13 to use PolicyPal.", county_fips: "Choose your county." } });

    expect(screen.getByLabelText("Date of birth")).toHaveAccessibleDescription("You must be at least 13 to use PolicyPal.");
    expect(screen.getByLabelText("County")).toHaveAccessibleDescription("Choose your county.");
  });

  it("passes a typed ZIP code up", async () => {
    const fields = renderFields({}, { values: { zipCode: "" } });

    await userEvent.type(screen.getByLabelText("ZIP code"), "7");

    expect(fields.setZipCode).toHaveBeenCalledWith("7");
  });
});
