/**
 * Where a hover popover goes, given the element it belongs to and its own size.
 *
 * It opens below the anchor, left edges aligned, and moves left as far as it must
 * to stay inside the viewport. It opens above the anchor instead when there is no
 * room below and there is room above.
 */

export const VIEWPORT_MARGIN_PX = 8;
export const ANCHOR_GAP_PX = 4;

export type AnchorBox = { left: number; top: number; bottom: number };

export type PopoverPosition = { left: number; top: number };

export function placePopover({
  anchor,
  width,
  height,
  viewportWidth,
  viewportHeight,
}: {
  anchor: AnchorBox;
  width: number;
  height: number;
  viewportWidth: number;
  viewportHeight: number;
}): PopoverPosition {
  const rightmostLeft = viewportWidth - VIEWPORT_MARGIN_PX - width;
  const left = Math.max(VIEWPORT_MARGIN_PX, Math.min(anchor.left, rightmostLeft));
  const below = anchor.bottom + ANCHOR_GAP_PX;
  const above = anchor.top - ANCHOR_GAP_PX - height;
  const fitsBelow = below + height <= viewportHeight - VIEWPORT_MARGIN_PX;
  if (fitsBelow || above < VIEWPORT_MARGIN_PX) {
    return { left, top: below };
  }
  return { left, top: above };
}
