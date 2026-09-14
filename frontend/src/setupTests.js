import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";

// jsdom doesn't implement scrollIntoView; components use it to keep the latest message in view.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// The session is restored from sessionStorage on mount, so a signed-in test
// would otherwise leak into the next one.
beforeEach(() => {
  sessionStorage.clear();
});
