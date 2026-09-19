import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { useProfile } from "../features/profile/useProfile";
import ProfilePage from "./ProfilePage";

vi.mock("../features/profile/useProfile");
vi.mock("../features/profile/ProfileForm", () => ({
  default: ({ profile }) => <div data-testid="profile-form">{profile.zip_code}</div>,
}));

function renderPage(state) {
  useProfile.mockReturnValue({ profile: null, counties: undefined, error: "", retry: vi.fn(), save: vi.fn(), ...state });
  render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>,
  );
}

describe("ProfilePage", () => {
  it("says it is loading", () => {
    renderPage({ status: "loading" });
    expect(screen.getByRole("status")).toHaveTextContent("Loading your profile…");
  });

  it("offers a retry when loading fails", async () => {
    const retry = vi.fn();
    renderPage({ status: "error", error: "Something went wrong.", retry });

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalled();
  });

  it("shows the form, a way back, and what happens to the data", () => {
    renderPage({ status: "ready", profile: { zip_code: "75801" } });

    expect(screen.getByTestId("profile-form")).toHaveTextContent("75801");
    expect(screen.getByRole("link", { name: /Back to your questions/ })).toHaveAttribute("href", "/chat");
    expect(screen.getByText(/never sent to the AI model/)).toBeInTheDocument();
  });
});
