import { expect, it } from "vitest";
import { apiError } from "./api-error";

it("reads a handler's own refusal from a string detail", () => {
  const error = apiError({ detail: "Run not found" }, "Failed to fetch run detail");

  expect(error.message).toBe("Run not found");
});

it("reads a validation list as one line per field, not as [object Object]", () => {
  const error = apiError(
    {
      detail: [
        { loc: ["body", "metrics"], msg: "List should have at least 1 item" },
        { loc: ["body", "model"], msg: "Field required" },
      ],
    },
    "Failed to start evaluation"
  );

  expect(error.message).toBe("metrics: List should have at least 1 item; model: Field required");
});

it("falls back when the body carries no detail", () => {
  expect(apiError({}, "Failed to save note").message).toBe("Failed to save note");
  expect(apiError("Internal Server Error", "Failed to save note").message).toBe(
    "Failed to save note"
  );
  expect(apiError({ detail: [] }, "Failed to save note").message).toBe("Failed to save note");
});
