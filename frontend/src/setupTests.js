import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollIntoView; components use it to keep the latest message in view.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
