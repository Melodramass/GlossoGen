// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { notifyManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LabelPickerModal } from "./label-picker-modal";

type ApiResult = Promise<{ data?: unknown; error?: unknown }>;

const { get, put } = vi.hoisted(() => ({
  get: vi.fn<(path: string) => ApiResult>(),
  put: vi.fn<(path: string, init: unknown) => ApiResult>(),
}));
vi.mock("@/shared/lib/api-client", () => ({ api: { GET: get, PUT: put, DELETE: vi.fn() } }));

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

// Deliver React Query notifications synchronously so `act` flushes a settled
// request into the DOM with no timer to wait on.
notifyManager.setScheduler(callback => callback());

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  get.mockReset();
  put.mockReset();
  get.mockResolvedValue({ data: { labels: ["baseline"] } });
});

afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
  vi.unstubAllGlobals();
});

async function renderPicker() {
  await act(async () => {
    root.render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(LabelPickerModal, {
          runId: "veyru/1700000000",
          currentLabels: [],
          onClose: () => {},
        })
      )
    );
  });
}

function baselineToggle(): HTMLButtonElement {
  const toggle = Array.from(document.body.querySelectorAll("button")).find(
    button => button.textContent === "baseline"
  );
  expect(toggle).toBeDefined();
  return toggle!;
}

function baselineTicked(): boolean {
  // The checkbox span carries bg-primary while the label counts as selected.
  return baselineToggle().querySelector("span")!.className.includes("bg-primary");
}

async function toggleBaseline() {
  await act(async () => {
    baselineToggle().click();
  });
}

it("shows the server's reason and refreshes nothing when a label save fails", async () => {
  put.mockResolvedValue({ error: { detail: "Could not write labels.json" } });
  await renderPicker();
  const invalidate = vi.spyOn(client, "invalidateQueries");

  await toggleBaseline();

  expect(put).toHaveBeenCalledTimes(1);
  expect(invalidate).not.toHaveBeenCalled();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toBe(
    "Could not write labels.json"
  );
});

it("refreshes the label lists when a label save succeeds", async () => {
  put.mockResolvedValue({ data: { labels: ["baseline"] } });
  await renderPicker();
  const invalidate = vi.spyOn(client, "invalidateQueries");

  await toggleBaseline();

  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["runs"] });
  expect(document.body.querySelector('[role="alert"]')).toBeNull();
});

it("unticks the label again when the server refuses the save", async () => {
  put.mockResolvedValue({ error: { detail: "Could not write labels.json" } });
  await renderPicker();

  await toggleBaseline();

  expect(baselineTicked()).toBe(false);
});

it("clears a failed save's error once a later save succeeds", async () => {
  put.mockResolvedValueOnce({ error: { detail: "Could not write labels.json" } });
  await renderPicker();
  await toggleBaseline();
  expect(document.body.querySelector('[role="alert"]')).not.toBeNull();

  put.mockResolvedValueOnce({ data: { labels: ["baseline"] } });
  await toggleBaseline();

  expect(baselineTicked()).toBe(true);
  expect(document.body.querySelector('[role="alert"]')).toBeNull();
});
