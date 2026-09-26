import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Exchange from "./Exchange";

const notice =
  "Summaries of Benefits and Coverage quoted here for Covered California plans are for each plan's standard version; people who qualify for cost-sharing reductions or American Indian and Alaska Native cost sharing pay less than they show.";

const question = { id: "q1", role: "user", content: "What do plans 1 and 2 charge?", created_at: "2026-09-26T14:16:00Z" };
const answer = {
  id: "a1",
  role: "assistant",
  content: `${notice}\n\nA $50 copay.[Source: wiki_Health.txt]`,
  created_at: "2026-09-26T14:16:30Z",
  sources: [{ id: "s1", source: "wiki_Health.txt", relevance: 0.9 }],
  plans: [],
};

const plan = {
  hios_plan_id: "p1", plan_year: 2026, name: "Value Silver", issuer: "CHRISTUS", metal_level: "Silver", plan_type: "HMO",
  monthly_premium: "620.15", premium_age: 34, premium_reference: "535.35", deductible: "5990.00", drug_deductible: null,
  out_of_pocket_max: "5990.00", hsa_eligible: false, quality_rating: 3, county_name: "Anderson", state: "TX", benefits_url: null,
};

function renderExchange(props = {}) {
  const handlers = { onOpenSource: vi.fn(), onHoverSource: vi.fn(), onAskAgain: vi.fn(), onAskAboutPlan: vi.fn() };
  const view = render(<Exchange exchange={{ key: "q1", question, answer }} {...handlers} {...props} />);
  return { ...view, ...handlers };
}

describe("Exchange", () => {
  it("sets the question as a serif heading, with its time", () => {
    renderExchange();
    const heading = screen.getByRole("heading", { level: 2, name: question.content });
    expect(heading.closest(".q")).toBeInTheDocument();
    expect(heading.closest(".q").querySelector("time")).toHaveAttribute("dateTime", question.created_at);
  });

  it("is a labelled section", () => {
    renderExchange();
    expect(screen.getByRole("region", { name: "Question and answer" })).toBeInTheDocument();
  });

  it("renders the answer's notice as a note and the rest as the answer", () => {
    renderExchange();
    expect(screen.getByRole("note")).toHaveTextContent(notice);
    expect(screen.getByText(/A \$50 copay\./)).toBeInTheDocument();
  });

  it("opens a source with its message", async () => {
    const { onOpenSource } = renderExchange();
    await userEvent.click(screen.getAllByRole("button", { name: "Source 1" })[0]);
    expect(onOpenSource).toHaveBeenCalledWith(answer, "s1");
  });

  it("stamps the seals only for the answer that just finished", () => {
    const { container, rerender } = renderExchange();
    expect(container.querySelector(".stamp")).toBeNull();
    rerender(<Exchange exchange={{ key: "q1", question, answer }} stamp onOpenSource={vi.fn()} />);
    expect(container.querySelector(".stamp")).not.toBeNull();
  });

  it("shows the plan table between the answer's first paragraph and the rest", () => {
    renderExchange({ exchange: { key: "q1", question, answer: { ...answer, content: "Here they are.\n\nAll have a deductible.", plans: [plan] } } });
    const body = screen.getByRole("table").closest(".a");
    const texts = [...body.children].map((el) => (el.querySelector("table") ? "TABLE" : el.textContent));
    expect(texts).toEqual(["Here they are.", "TABLE", "All have a deductible."]);
  });

  it("never links a user's own question", () => {
    renderExchange({ exchange: { key: "q1", question: { ...question, content: "Is https://example.com/sbc.pdf right?" }, answer: null } });
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows no plan table for an answer without plans", () => {
    renderExchange();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the live answer while it streams", () => {
    renderExchange({
      exchange: { key: "q1", question, answer: null },
      live: { questionId: "q1", stages: ["searching"], notices: [], text: "" },
    });
    expect(screen.getByRole("list", { name: "Progress" })).toBeInTheDocument();
  });

  it("says a stopped answer was stopped, and can ask again", async () => {
    const { onAskAgain } = renderExchange({ exchange: { key: "q1", question, answer: null }, stopped: true });
    const note = screen.getByText("You stopped this answer.");
    await userEvent.click(within(note.parentElement).getByRole("button", { name: "Ask again" }));
    expect(onAskAgain).toHaveBeenCalledWith(question.content);
  });

  it("shows an answer with no question before it", () => {
    renderExchange({ exchange: { key: "a1", question: null, answer } });
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
    expect(screen.getByText(/A \$50 copay\./)).toBeInTheDocument();
  });
});
