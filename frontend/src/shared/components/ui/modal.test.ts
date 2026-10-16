// @vitest-environment jsdom
import { act, createElement, StrictMode, type ReactNode } from "react";
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

function modal(label: string, onClose: () => void, children: ReactNode) {
  // A .ts file has no JSX, and the props type requires `children`.
  // eslint-disable-next-line react/no-children-prop
  return createElement(Modal, {
    label,
    width: "md",
    panelClassName: "p-4",
    panelId: null,
    onClose,
    children,
  });
}

async function render(element: ReactNode) {
  await act(async () => root.render(element));
}

function dialog(label: string): HTMLElement {
  const element = document.body.querySelector<HTMLElement>(
    `[role="dialog"][aria-label="${label}"]`
  );
  if (element === null) {
    throw new Error(`no dialog labelled ${label}`);
  }
  return element;
}

function pressEscape(target: EventTarget) {
  act(() => {
    target.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
}

it("renders an accessible dialog into document.body", async () => {
  await render(modal("Notes", () => {}, "body text"));

  const panel = dialog("Notes");
  expect(panel.getAttribute("aria-modal")).toBe("true");
  expect(container.contains(panel)).toBe(false);
  expect(panel.textContent).toBe("body text");
});

it("closes on Escape", async () => {
  const onClose = vi.fn();
  await render(modal("Notes", onClose, "body"));

  pressEscape(document.body);

  expect(onClose).toHaveBeenCalledTimes(1);
});

it("ignores other keys", async () => {
  const onClose = vi.fn();
  await render(modal("Notes", onClose, "body"));

  act(() => {
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });

  expect(onClose).not.toHaveBeenCalled();
});

it("closes on a click on the backdrop", async () => {
  const onClose = vi.fn();
  await render(modal("Notes", onClose, "body"));

  const backdrop = dialog("Notes").closest<HTMLElement>('[role="presentation"]');
  act(() => backdrop?.click());

  expect(onClose).toHaveBeenCalledTimes(1);
});

it("stays open on a click inside the panel", async () => {
  const onClose = vi.fn();
  await render(modal("Notes", onClose, createElement("button", { type: "button" }, "inside")));

  act(() => dialog("Notes").querySelector("button")?.click());
  act(() => dialog("Notes").click());

  expect(onClose).not.toHaveBeenCalled();
});

it("closes only the topmost of two stacked modals on Escape", async () => {
  const closeLower = vi.fn();
  const closeUpper = vi.fn();
  await render(
    createElement(
      "div",
      null,
      modal("Lower", closeLower, "lower"),
      modal("Upper", closeUpper, "upper")
    )
  );

  pressEscape(document.body);

  expect(closeUpper).toHaveBeenCalledTimes(1);
  expect(closeLower).not.toHaveBeenCalled();
});

it("hands Escape to the modal below once the topmost one unmounts", async () => {
  const closeLower = vi.fn();
  await render(
    createElement(
      "div",
      null,
      modal("Lower", closeLower, "lower"),
      modal("Upper", () => {}, "upper")
    )
  );

  await render(createElement("div", null, modal("Lower", closeLower, "lower"), null));
  pressEscape(document.body);

  expect(closeLower).toHaveBeenCalledTimes(1);
});

it("closes the topmost modal when it was opened from inside the lower one", async () => {
  const closeLower = vi.fn();
  const closeUpper = vi.fn();
  await render(modal("Lower", closeLower, "lower"));
  await render(modal("Lower", closeLower, modal("Upper", closeUpper, "upper")));

  pressEscape(dialog("Upper"));

  expect(closeUpper).toHaveBeenCalledTimes(1);
  expect(closeLower).not.toHaveBeenCalled();
});

it("stays open when a field inside handles Escape and stops it", async () => {
  const onClose = vi.fn();
  const field = createElement("input", {
    onKeyDown: (event: React.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
      }
    },
  });
  await render(modal("Notes", onClose, field));

  pressEscape(dialog("Notes").querySelector("input") as HTMLInputElement);

  expect(onClose).not.toHaveBeenCalled();
});

it("moves focus to the panel on open and back to the trigger on close", async () => {
  const trigger = document.createElement("button");
  document.body.appendChild(trigger);
  trigger.focus();

  await render(modal("Notes", () => {}, "body"));
  expect(document.activeElement).toBe(dialog("Notes"));

  await render(null);
  expect(document.activeElement).toBe(trigger);
  trigger.remove();
});

it("leaves focus on a child that took it with autoFocus", async () => {
  await render(modal("Notes", () => {}, createElement("input", { autoFocus: true })));

  expect(document.activeElement).toBe(dialog("Notes").querySelector("input"));
});

it("keeps focus on an autoFocus child under StrictMode", async () => {
  const trigger = document.createElement("button");
  document.body.appendChild(trigger);
  trigger.focus();

  await render(
    createElement(
      StrictMode,
      null,
      modal("Notes", () => {}, createElement("input", { autoFocus: true }))
    )
  );
  expect(document.activeElement).toBe(dialog("Notes").querySelector("input"));

  await render(null);
  expect(document.activeElement).toBe(trigger);
  trigger.remove();
});
