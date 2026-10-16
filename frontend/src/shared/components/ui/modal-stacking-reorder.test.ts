// @vitest-environment jsdom
import { act, createElement, memo, useState } from "react";
import { flushSync } from "react-dom";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Modal } from "./modal";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

// A browser runs a microtask checkpoint between two listeners of a key event
// the user pressed, and React flushes a discrete update in a microtask. The
// test's synchronous dispatchEvent never reaches that checkpoint, so the
// upper modal's onClose commits with flushSync to stand in for it.
it("closes only the topmost when the lower modal re-rendered after the upper opened", async () => {
  const closeLower = vi.fn();
  let rerenderLower: () => void = () => {};

  // The upper modal's open state lives in its own component, as a modal
  // opened from a row or a button inside the page does.
  const UpperOwner = memo(function UpperOwner() {
    const [open, setOpen] = useState(true);
    const [close] = useState(() => () => flushSync(() => setOpen(false)));
    if (!open) {
      return null;
    }
    // eslint-disable-next-line react/no-children-prop
    return createElement(Modal, {
      label: "Upper",
      width: "md",
      panelClassName: "",
      panelId: null,
      onClose: close,
      children: "upper",
    });
  });

  function Page() {
    const [, setTick] = useState(0);
    rerenderLower = () => setTick(tick => tick + 1);
    return createElement(
      "div",
      null,
      // Inline onClose, as every caller in the app passes one.
      // eslint-disable-next-line react/no-children-prop
      createElement(Modal, {
        label: "Lower",
        width: "md",
        panelClassName: "",
        panelId: null,
        onClose: () => closeLower(),
        children: "lower",
      }),
      createElement(UpperOwner)
    );
  }

  await act(async () => root.render(createElement(Page)));
  // Any re-render of the lower modal's owner (a query refetch, a keystroke)
  // re-adds its window listener behind the upper one's.
  await act(async () => rerenderLower());

  act(() => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });

  expect(document.body.querySelector('[aria-label="Upper"]')).toBeNull();
  expect(closeLower).not.toHaveBeenCalled();
});
