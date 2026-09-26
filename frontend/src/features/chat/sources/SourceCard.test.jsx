import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../../hooks/useAuth";
import * as chatService from "../../../services/chatService";
import SourceCard from "./SourceCard";
import { clearSourceCache } from "./useSource";

vi.mock("../../../hooks/useAuth");
vi.mock("../../../services/chatService");

const source = { id: "s1", source: "Sharp Silver 70 Premier HMO - Summary of Benefits - Urgent.pdf", chunk_id: "sbc_1", relevance: 0.94 };

const sbc = {
  id: "s1",
  kind: "sbc",
  title: "Sharp Silver 70 Premier HMO",
  document: "Summary of Benefits and Coverage, 2026",
  section: "If you need immediate medical attention",
  quote: "Urgent care | $50 copay/visit; deductible does not apply | …",
  status: "ok",
  url: "https://www.sharphealthplan.com/sbc.pdf",
  license: null,
};

const wiki = {
  id: "s2",
  kind: "wikipedia",
  title: "Health insurance",
  document: "Wikipedia article",
  section: null,
  quote: "Health insurance or medical insurance is a type of insurance …",
  status: "ok",
  url: "https://en.wikipedia.org/wiki/Health_insurance",
  license: { name: "CC BY-SA 4.0", url: "https://creativecommons.org/licenses/by-sa/4.0/" },
};

function renderCard(passage, props = {}) {
  chatService.getSource.mockResolvedValue(passage);
  const onSelect = vi.fn();
  render(<SourceCard source={source} number={1} onSelect={onSelect} {...props} />);
  return { onSelect };
}

beforeEach(() => {
  vi.clearAllMocks();
  clearSourceCache();
  useAuth.mockReturnValue({ token: "tok", expireSession: vi.fn() });
});

describe("SourceCard", () => {
  it("shows the source's label while its passage loads", () => {
    chatService.getSource.mockReturnValue(new Promise(() => {}));
    render(<SourceCard source={source} number={1} onSelect={vi.fn()} />);
    expect(screen.getByText("Loading the passage…")).toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveTextContent("Sharp Silver 70 Premier HMO - Summary of Benefits - Urgent");
  });

  it("ok: the quote, the match meter and the carrier's PDF", async () => {
    renderCard(sbc);
    expect(await screen.findByText("Sharp Silver 70 Premier HMO")).toBeInTheDocument();
    expect(screen.getByText("Summary of Benefits and Coverage, 2026. If you need immediate medical attention")).toBeInTheDocument();
    const quote = document.querySelector(".quote");
    expect(quote).toHaveTextContent("Urgent care | $50 copay/visit; deductible does not apply | …");
    expect(quote.querySelectorAll(".muted")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "94% match" })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Carrier's PDF/ });
    expect(link).toHaveAttribute("href", sbc.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("ok, Wikipedia: Read on Wikipedia, and the licence credit", async () => {
    renderCard(wiki);
    const link = await screen.findByRole("link", { name: /Read on Wikipedia/ });
    expect(link).toHaveAttribute("href", wiki.url);
    const credit = screen.getByText(/Text from the Wikipedia article/);
    expect(credit).toHaveTextContent("Text from the Wikipedia article “Health insurance”, by its contributors, under CC BY-SA 4.0.");
    const licence = screen.getByRole("link", { name: /CC BY-SA 4.0/ });
    expect(licence).toHaveAttribute("href", wiki.license.url);
    expect(licence).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("unverified: the quote, and a warning that it may have changed", async () => {
    renderCard({ ...sbc, status: "unverified" });
    expect(await screen.findByText("This passage may have changed since the answer.")).toBeInTheDocument();
    expect(document.querySelector(".quote")).not.toBeNull();
  });

  it.each(["changed", "missing"])("%s: no quote, and why", async (status) => {
    renderCard({ ...wiki, status, quote: null });
    expect(await screen.findByText("This passage has changed since the answer and can't be shown.")).toBeInTheDocument();
    expect(document.querySelector(".quote")).toBeNull();
    expect(screen.queryByText(/Text from the Wikipedia article/)).not.toBeInTheDocument();
  });

  it("links nothing when the passage has no safe https link", async () => {
    renderCard({ ...sbc, url: "javascript:alert(1)" });
    await screen.findByText("Sharp Silver 70 Premier HMO");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("says when the passage couldn't be loaded, and tries again", async () => {
    chatService.getSource.mockRejectedValueOnce(new Error("Something went wrong."));
    render(<SourceCard source={source} number={1} onSelect={vi.fn()} />);
    expect(await screen.findByText("This source couldn't be loaded.")).toBeInTheDocument();
    chatService.getSource.mockResolvedValueOnce(sbc);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("Sharp Silver 70 Premier HMO")).toBeInTheDocument());
  });

  it("marks the selected and hovered card, and selects on click", async () => {
    const { onSelect } = renderCard(sbc, { selected: true, hovered: true });
    const card = screen.getByRole("article");
    expect(card).toHaveAttribute("aria-current", "true");
    expect(card).toHaveClass("src", "sel", "hover");
    await userEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith("s1");
  });
});
