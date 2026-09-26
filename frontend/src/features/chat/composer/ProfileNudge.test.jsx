import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import ProfileNudge from "./ProfileNudge";

describe("ProfileNudge", () => {
  it("asks for a ZIP code and date of birth, linking to the profile", () => {
    render(
      <MemoryRouter>
        <ProfileNudge />
      </MemoryRouter>,
    );
    expect(screen.getByText(/To compare plans you can buy, add your ZIP code and date of birth in/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "your profile" })).toHaveAttribute("href", "/profile");
  });
});
