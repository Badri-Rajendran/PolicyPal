import { afterEach, describe, expect, it, vi } from "vitest";
import { trapTab } from "./focus";

function layer(html) {
  const container = document.createElement("div");
  container.innerHTML = html;
  document.body.append(container);
  return container;
}

function tab(container, shiftKey = false) {
  const event = { key: "Tab", shiftKey, preventDefault: vi.fn() };
  trapTab(event, container);
  return event;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("trapTab", () => {
  it("wraps from the last element to the first, and back with Shift", () => {
    const container = layer('<button>One</button><input aria-label="Two" /><a href="#">Three</a>');
    const [one, , three] = container.querySelectorAll("button, input, a");

    three.focus();
    expect(tab(container).preventDefault).toHaveBeenCalled();
    expect(one).toHaveFocus();

    tab(container, true);
    expect(three).toHaveFocus();
  });

  it("moves on from an element outside the tab order, such as a selected card", () => {
    const container = layer('<button>One</button><div tabindex="-1">Card</div><button>Two</button>');
    container.querySelector("div").focus();

    tab(container);
    expect(container.querySelectorAll("button")[1]).toHaveFocus();
  });

  it("skips disabled controls and leaves other keys alone", () => {
    const container = layer("<button>One</button><button disabled>Off</button><button>Two</button>");
    const [one, , two] = container.querySelectorAll("button");
    one.focus();

    tab(container);
    expect(two).toHaveFocus();
    const other = { key: "Enter", preventDefault: vi.fn() };
    trapTab(other, container);
    expect(other.preventDefault).not.toHaveBeenCalled();
  });
});
