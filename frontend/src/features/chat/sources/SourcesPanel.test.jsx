import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../../hooks/useAuth";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import * as chatService from "../../../services/chatService";
import SourcesPanel from "./SourcesPanel";
import { clearSourceCache } from "./useSource";

vi.mock("../../../hooks/useAuth");
vi.mock("../../../hooks/useMediaQuery");
vi.mock("../../../services/chatService");

const message = {
  id: "a1",
  role: "assistant",
  sources: [
    { id: "s1", source: "wiki_Health_insurance.txt", relevance: 0.88 },
    { id: "s2", source: "wiki_Health_insurance.txt", relevance: 0.8 },
    { id: "s3", source: "hcg_glossary_Copayment.md", relevance: 0.7 },
  ],
};

function renderPanel(props = {}) {
  const handlers = { onSelect: vi.fn(), onClose: vi.fn() };
  render(
    <>
      <button type="button">Seal</button>
      <SourcesPanel message={message} selectedSourceId="s3" hoveredSourceId={null} {...handlers} {...props} />
    </>,
  );
  return handlers;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearSourceCache();
  useAuth.mockReturnValue({ token: "tok", expireSession: vi.fn() });
  useMediaQuery.mockReturnValue(false);
  chatService.getSource.mockImplementation(async (_t, id) => ({
    id,
    kind: "other",
    title: `Title ${id}`,
    document: null,
    section: null,
    quote: `Quote ${id}`,
    status: "ok",
    url: null,
    license: null,
  }));
});

describe("SourcesPanel", () => {
  it("is a labelled column with a heading", () => {
    renderPanel();
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(within(panel).getByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lists a card per source, numbered as the seals are", async () => {
    renderPanel();
    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(3);
    expect(cards.map((c) => c.querySelector(".seal").textContent)).toEqual(["1", "1", "2"]);
    expect(await screen.findByText("Quote s3")).toBeInTheDocument();
  });

  it("marks the selected card and scrolls it into view", () => {
    const scrollIntoView = vi.spyOn(Element.prototype, "scrollIntoView");
    renderPanel();
    const selected = screen.getAllByRole("article")[2];
    expect(selected).toHaveAttribute("aria-current", "true");
    expect(scrollIntoView.mock.contexts).toContain(selected);
    scrollIntoView.mockRestore();
  });

  it("moves focus into the panel when it opens", () => {
    renderPanel();
    expect(screen.getAllByRole("article")[2]).toHaveFocus();
  });

  it("closes from its close button", async () => {
    const { onClose } = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Close sources" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("closes on Escape", async () => {
    const { onClose } = renderPanel();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("selects a card when clicked", async () => {
    const { onSelect } = renderPanel();
    await userEvent.click(screen.getAllByRole("article")[0]);
    expect(onSelect).toHaveBeenCalledWith("s1");
  });

  describe("on a phone", () => {
    beforeEach(() => {
      useMediaQuery.mockReturnValue(true);
    });

    it("is a dialog named Sources, with focus moved into it", () => {
      renderPanel();
      const dialog = screen.getByRole("dialog", { name: "Sources" });
      expect(dialog).toHaveAttribute("aria-modal", "true");
      expect(dialog).toContainElement(document.activeElement);
    });

    it("closes on Escape and from the scrim", async () => {
      const { onClose } = renderPanel();
      await userEvent.keyboard("{Escape}");
      expect(onClose).toHaveBeenCalledTimes(1);
      await userEvent.click(document.querySelector(".scrim"));
      expect(onClose).toHaveBeenCalledTimes(2);
    });

    it("keeps Tab inside the sheet", async () => {
      renderPanel();
      const dialog = screen.getByRole("dialog");
      for (let i = 0; i < 6; i += 1) {
        await userEvent.tab();
        expect(dialog).toContainElement(document.activeElement);
      }
    });
  });
});
