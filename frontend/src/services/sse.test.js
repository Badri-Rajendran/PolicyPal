import { describe, expect, it, vi } from "vitest";
import { createSseParser } from "./sse";

describe("createSseParser", () => {
  it("parses events split across chunks", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);
    parser.push('event: delta\ndata: {"te');
    parser.push('xt":"Hi"}\n\nevent: stage\ndata: {"stage":"writing"}\n\n');
    expect(onEvent.mock.calls.map(([e]) => e)).toEqual([
      { event: "delta", data: { text: "Hi" } },
      { event: "stage", data: { stage: "writing" } },
    ]);
  });

  it("parses several events in one chunk", () => {
    const onEvent = vi.fn();
    createSseParser(onEvent).push(
      'event: delta\ndata: {"text":"a"}\n\nevent: delta\ndata: {"text":"b"}\n\nevent: reset\ndata: {}\n\n',
    );
    expect(onEvent.mock.calls.map(([e]) => e.event)).toEqual(["delta", "delta", "reset"]);
  });

  it("dispatches a final event with no blank line on end()", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);
    parser.push('event: done\ndata: {"ok":true}');
    expect(onEvent).not.toHaveBeenCalled();
    parser.end();
    expect(onEvent).toHaveBeenCalledWith({ event: "done", data: { ok: true } });
  });

  it("accepts CRLF line endings", () => {
    const onEvent = vi.fn();
    createSseParser(onEvent).push("event: reset\r\ndata: {}\r\n\r\n");
    expect(onEvent).toHaveBeenCalledWith({ event: "reset", data: {} });
  });

  it("ignores comments and blocks without data", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);
    parser.push(": keep-alive\n\nevent: stage\n\n");
    parser.end();
    expect(onEvent).not.toHaveBeenCalled();
  });
});
