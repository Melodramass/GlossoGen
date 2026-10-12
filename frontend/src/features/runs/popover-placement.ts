/**
 * Where a hover popover goes, given the element it belongs to and its own size.
 *
 * It opens below the anchor, left edges aligned, and moves left as far as it must
 * to stay inside the viewport. It opens above the anchor instead when it does not
 * fit below and there is more room above. Its height is capped to the room on the
 * side it opens on, so a popover taller than that room scrolls instead of running
 * past the viewport.
 */

export const VIEWPORT_MARGIN_PX = 8;
export const ANCHOR_GAP_PX = 4;

export type AnchorBox = { left: number; top: number; bottom: number };

export type PopoverPosition = { left: number; top: number; maxHeight: number };

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
  const roomBelow = viewportHeight - VIEWPORT_MARGIN_PX - below;
  const roomAbove = anchor.top - ANCHOR_GAP_PX - VIEWPORT_MARGIN_PX;
  if (height > roomBelow && roomAbove > roomBelow) {
    const shownHeight = Math.min(height, roomAbove);
    return { left, top: anchor.top - ANCHOR_GAP_PX - shownHeight, maxHeight: roomAbove };
  }
  return { left, top: below, maxHeight: roomBelow };
}
