// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { notifyManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GROUP_LABELS_QUERY_KEY, useGroupLabels } from "./use-group-labels";

const { get } = vi.hoisted(() => ({
  get: vi.fn<(path: string) => Promise<{ data?: unknown; error?: unknown }>>(),
}));
vi.mock("@/shared/lib/api-client", () => ({ api: { GET: get } }));

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

// React Query batches observer notifications on a zero-delay timer by default. Delivering
// them synchronously lets `act` flush a resolved request into the DOM with no timer to wait on.
notifyManager.setScheduler(callback => callback());

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  get.mockReset();
});

afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
  vi.unstubAllGlobals();
});

function Consumer({ name }: { name: string }) {
  const { data, isError } = useGroupLabels();
  const text = isError ? "error" : (data ?? []).join(",");
  return createElement("p", { "data-consumer": name }, text);
}

function shown(name: string): string | null | undefined {
  return container.querySelector(`[data-consumer="${name}"]`)?.textContent;
}

async function renderTwoConsumers() {
  await act(async () => {
    root.render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(Consumer, { name: "run-list" }),
        createElement(Consumer, { name: "analysis-panel" })
      )
    );
  });
}

it("serves every consumer from one request", async () => {
  get.mockResolvedValue({ data: { labels: ["baseline", "budget=800"] } });

  await renderTwoConsumers();

  expect(get).toHaveBeenCalledTimes(1);
  expect(shown("run-list")).toBe("baseline,budget=800");
  expect(shown("analysis-panel")).toBe("baseline,budget=800");
});

it("refreshes every consumer when a label edit invalidates the shared key", async () => {
  get.mockResolvedValue({ data: { labels: ["baseline"] } });
  await renderTwoConsumers();

  get.mockResolvedValue({ data: { labels: ["baseline", "e2e_new"] } });
  await act(async () => {
    await client.invalidateQueries({ queryKey: GROUP_LABELS_QUERY_KEY });
  });

  expect(shown("run-list")).toBe("baseline,e2e_new");
  expect(shown("analysis-panel")).toBe("baseline,e2e_new");
});

it("reports a failed request as an error rather than an empty list", async () => {
  get.mockResolvedValue({ error: { detail: "boom" } });

  await renderTwoConsumers();

  expect(shown("run-list")).toBe("error");
});
