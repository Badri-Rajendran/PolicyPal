import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AnswerFooter from "./AnswerFooter";

const message = {
  id: "a1",
  role: "assistant",
  content: "Fifty dollars.[Source: wiki_Health_insurance.txt] See [Plan: p1].",
  sources: [
    { id: "s1", source: "wiki_Health_insurance.txt", relevance: 0.9 },
    { id: "s2", source: "wiki_Health_insurance.txt", relevance: 0.7 },
    { id: "s3", source: "hcg_glossary_Copayment.md", relevance: 0.6 },
  ],
  plans: [{ hios_plan_id: "p1", name: "Sharp Silver 70 Premier HMO" }],
};

let writeText;

beforeEach(() => {
  vi.useFakeTimers();
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
});

async function clickCopy() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
  });
}

describe("AnswerFooter", () => {
  it("shows a chip per cited document, numbered as the seals are, that opens it", () => {
    const onOpenSource = vi.fn();
    render(<AnswerFooter message={message} onOpenSource={onOpenSource} />);
    const chips = screen.getAllByRole("button", { name: /^Source / });
    expect(chips.map((c) => c.textContent)).toEqual(["1Health insurance", "2Copayment"]);
    fireEvent.click(chips[1]);
    expect(onOpenSource).toHaveBeenCalledWith("s3");
  });

  it("has no chips for an answer without sources", () => {
    render(<AnswerFooter message={{ ...message, sources: [] }} onOpenSource={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /^Source / })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
  });

  it("copies the answer as plain text and says Copied for 1.6 s", async () => {
    render(<AnswerFooter message={message} onOpenSource={vi.fn()} />);
    await clickCopy();
    expect(writeText).toHaveBeenCalledWith("Fifty dollars.[1] See Sharp Silver 70 Premier HMO.");
    expect(screen.getByRole("button", { name: "Copy answer" })).toHaveTextContent("Copied");
    act(() => vi.advanceTimersByTime(1600));
    expect(screen.getByRole("button", { name: "Copy answer" })).toHaveTextContent("Copy");
    expect(screen.getByRole("button", { name: "Copy answer" })).not.toHaveTextContent("Copied");
  });

  it("says when it couldn't copy", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    render(<AnswerFooter message={message} onOpenSource={vi.fn()} />);
    await clickCopy();
    expect(screen.getByRole("button", { name: "Copy answer" })).toHaveTextContent("Couldn't copy");
  });

  it("says it couldn't copy when there's no clipboard", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    render(<AnswerFooter message={message} onOpenSource={vi.fn()} />);
    await clickCopy();
    expect(screen.getByRole("button", { name: "Copy answer" })).toHaveTextContent("Couldn't copy");
  });
});
