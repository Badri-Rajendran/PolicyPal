import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Transcript from "./Transcript";

const messages = [
  { id: "q1", role: "user", content: "What is a deductible?", created_at: "2026-01-01T00:00:00Z" },
  { id: "a1", role: "assistant", content: "It's the amount you pay first.", created_at: "2026-01-01T00:00:00Z", sources: [], plans: [] },
];

function renderTranscript(props = {}) {
  const handlers = {
    onPrompt: vi.fn(),
    onRetry: vi.fn(),
    onAskAgain: vi.fn(),
    onOpenSource: vi.fn(),
    onHoverSource: vi.fn(),
    onAskAboutPlan: vi.fn(),
  };
  const view = render(
    <Transcript messages={messages} status="ready" error="" live={null} stoppedId={null} finishedId={null} {...handlers} {...props} />,
  );
  return { ...view, ...handlers };
}

function scrollTo(scroller, { top, height = 2000, client = 600 }) {
  Object.defineProperty(scroller, "scrollHeight", { value: height, configurable: true });
  Object.defineProperty(scroller, "clientHeight", { value: client, configurable: true });
  scroller.scrollTop = top;
  fireEvent.scroll(scroller);
}

describe("Transcript", () => {
  it("shows a loading message while the thread loads", () => {
    renderTranscript({ messages: [], status: "loading" });
    expect(screen.getByText("Loading conversation…")).toBeInTheDocument();
  });

  it("reports a failed load instead of the empty state, and retries", async () => {
    const { onRetry } = renderTranscript({ messages: [], status: "error", error: "Something went wrong." });
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("falls back to its own wording when the failure carries no message", () => {
    renderTranscript({ messages: [], status: "error", error: "" });
    expect(screen.getByRole("alert")).toHaveTextContent("This conversation couldn't be loaded.");
  });

  it("shows the empty state for a thread with no messages", async () => {
    const { onPrompt } = renderTranscript({ messages: [], status: "ready" });
    expect(screen.getByRole("heading", { name: "What would you like to know about your coverage?" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Can I buy a plan outside open enrollment\?/ }));
    expect(onPrompt).toHaveBeenCalledWith("Can I buy a plan outside open enrollment?");
  });

  it("shows the empty state with no thread open", () => {
    renderTranscript({ messages: [], status: "idle" });
    expect(screen.getByRole("heading", { name: "What would you like to know about your coverage?" })).toBeInTheDocument();
  });

  it("pairs questions with their answers", () => {
    renderTranscript();
    expect(screen.getAllByRole("region", { name: "Question and answer" })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2, name: "What is a deductible?" })).toBeInTheDocument();
    expect(screen.getByText("It's the amount you pay first.")).toBeInTheDocument();
  });

  it("shows the live answer under its question", () => {
    renderTranscript({
      messages: [messages[0]],
      live: { questionId: "q1", stages: ["writing"], notices: [], text: "It's" },
    });
    expect(screen.getByRole("list", { name: "Progress" })).toBeInTheDocument();
  });

  it("says a stopped answer was stopped", async () => {
    const { onAskAgain } = renderTranscript({ messages: [messages[0]], stoppedId: "q1" });
    expect(screen.getByText("You stopped this answer.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ask again" }));
    expect(onAskAgain).toHaveBeenCalledWith("What is a deductible?");
  });

  it("stamps only the answer that just finished, never loaded history", () => {
    const { container, rerender } = renderTranscript({
      messages: [{ ...messages[0] }, { ...messages[1], content: "Yes.[Source: a.txt]", sources: [{ id: "s1", source: "a.txt", relevance: 1 }] }],
    });
    expect(container.querySelector(".stamp")).toBeNull();
    rerender(
      <Transcript
        messages={[{ ...messages[0] }, { ...messages[1], content: "Yes.[Source: a.txt]", sources: [{ id: "s1", source: "a.txt", relevance: 1 }] }]}
        status="ready"
        live={null}
        finishedId="a1"
        onOpenSource={vi.fn()}
      />,
    );
    expect(container.querySelector(".stamp")).not.toBeNull();
  });

  it("offers to jump to the latest answer when scrolled well above it", async () => {
    const scrollIntoView = vi.fn();
    const { container } = renderTranscript();
    const scroller = container.querySelector(".scroll");
    container.querySelector(".transcript-end").scrollIntoView = scrollIntoView;

    scrollTo(scroller, { top: 1250 }); // 150 px from the bottom
    expect(screen.queryByRole("button", { name: "Jump to latest" })).not.toBeInTheDocument();

    scrollTo(scroller, { top: 1000 }); // 400 px from the bottom
    await userEvent.click(screen.getByRole("button", { name: "Jump to latest" }));
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("keeps a streaming answer in view while you're at the bottom, and not once you scroll up", () => {
    const scrollIntoView = vi.fn();
    const live = { questionId: "q1", stages: ["writing"], notices: [], text: "It" };
    const props = { messages: [messages[0]], status: "ready", live, onOpenSource: vi.fn() };
    const { container, rerender } = render(<Transcript {...props} />);
    const end = container.querySelector(".transcript-end");
    end.scrollIntoView = scrollIntoView;

    rerender(<Transcript {...props} live={{ ...live, text: "It's the" }} />);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    scrollTo(container.querySelector(".scroll"), { top: 100 });
    rerender(<Transcript {...props} live={{ ...live, text: "It's the amount" }} />);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("announces a finished answer with its count of cited documents", () => {
    const sources = [
      { id: "s1", source: "Plan A - Summary of Benefits.pdf", chunk_id: "c1", relevance: 0.9 },
      { id: "s2", source: "Plan A - Summary of Benefits.pdf", chunk_id: "c2", relevance: 0.8 },
      { id: "s3", source: "wiki_Copayment.txt", chunk_id: "c3", relevance: 0.7 },
    ];
    const cited = [messages[0], { ...messages[1], sources }];
    const { rerender } = renderTranscript({ messages: cited });
    const status = () => screen.getByRole("status");
    expect(status()).toBeEmptyDOMElement(); // history never announces

    rerender(<Transcript messages={cited} status="ready" finishedId="a1" onOpenSource={vi.fn()} />);
    expect(status()).toHaveTextContent("Answer ready, 2 sources");
  });

  it("says just that the answer is ready when it cites nothing, and stays quiet while one streams", () => {
    const live = { questionId: "q2", stages: ["writing"], notices: [], text: "It" };
    const { rerender } = renderTranscript({ finishedId: "a1" });
    const status = () => screen.getByRole("status");
    expect(status()).toHaveTextContent(/^Answer ready$/);

    const asked = [...messages, { id: "q2", role: "user", content: "And a copay?", created_at: "2026-01-01T00:01:00Z" }];
    rerender(<Transcript messages={asked} status="ready" live={live} finishedId="a1" onOpenSource={vi.fn()} />);
    expect(status()).toBeEmptyDOMElement();
  });

  it("shows a question you send even while scrolled up, then follows its answer", () => {
    const scrollIntoView = vi.fn();
    const props = { messages, status: "ready", live: null, onOpenSource: vi.fn() };
    const { container, rerender } = render(<Transcript {...props} />);
    container.querySelector(".transcript-end").scrollIntoView = scrollIntoView;
    const scroller = container.querySelector(".scroll");
    scrollTo(scroller, { top: 100 });

    const question = { id: "temp-1", role: "user", content: "And a copay?", created_at: "2026-01-01T00:01:00Z" };
    const live = { questionId: "temp-1", stages: [], notices: [], text: "" };
    rerender(<Transcript {...props} messages={[...messages, question]} live={live} />);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    rerender(<Transcript {...props} messages={[...messages, question]} live={{ ...live, text: "A copay" }} />);
    expect(scrollIntoView).toHaveBeenCalledTimes(2);

    scrollTo(scroller, { top: 100 }); // scrolling up again still stops the following
    rerender(<Transcript {...props} messages={[...messages, question]} live={{ ...live, text: "A copay is" }} />);
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });
});
