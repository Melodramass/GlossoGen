import { describe, expect, it } from "vitest";
import { ANCHOR_GAP_PX, VIEWPORT_MARGIN_PX, placePopover } from "./popover-placement";

/**
 * The evaluation badge sits at the right end of a run row, so a popover aligned to
 * its left edge ran past the viewport. These pin the popover inside it.
 */

const VIEWPORT = { viewportWidth: 1200, viewportHeight: 800 };

describe("placePopover", () => {
  it("opens below the anchor, left edges aligned, when it fits", () => {
    expect(
      placePopover({
        anchor: { left: 100, top: 50, bottom: 70 },
        width: 300,
        height: 200,
        ...VIEWPORT,
      })
    ).toEqual({ left: 100, top: 70 + ANCHOR_GAP_PX });
  });

  it("moves left to keep its right edge inside the viewport", () => {
    const position = placePopover({
      anchor: { left: 1150, top: 50, bottom: 70 },
      width: 400,
      height: 200,
      ...VIEWPORT,
    });
    expect(position.left + 400).toBe(1200 - VIEWPORT_MARGIN_PX);
  });

  it("never moves past the viewport's left margin, even when wider than the viewport", () => {
    expect(
      placePopover({
        anchor: { left: 50, top: 50, bottom: 70 },
        width: 1500,
        height: 100,
        ...VIEWPORT,
      }).left
    ).toBe(VIEWPORT_MARGIN_PX);
  });

  it("opens above the anchor when there is no room below and room above", () => {
    expect(
      placePopover({
        anchor: { left: 100, top: 700, bottom: 720 },
        width: 300,
        height: 200,
        ...VIEWPORT,
      }).top
    ).toBe(700 - ANCHOR_GAP_PX - 200);
  });

  it("stays below when there is room neither below nor above", () => {
    expect(
      placePopover({
        anchor: { left: 100, top: 100, bottom: 120 },
        width: 300,
        height: 750,
        ...VIEWPORT,
      }).top
    ).toBe(120 + ANCHOR_GAP_PX);
  });
});
