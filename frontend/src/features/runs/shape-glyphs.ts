/**
 * Glyphs and colors for scenarios whose objects are a colored shape on a grid.
 * Shared by those scenarios' round-detail panels so the same object reads the
 * same in every one.
 */

const SHAPE_GLYPH: Record<string, string> = {
  circle: "●",
  square: "■",
  triangle: "▲",
  star: "★",
};

const COLOR_HEX: Record<string, string> = {
  red: "#ef4444",
  blue: "#3b82f6",
  green: "#22c55e",
  yellow: "#eab308",
  purple: "#a855f7",
  orange: "#f97316",
  pink: "#ec4899",
  brown: "#a16207",
};

/** The glyph drawn for `shape`, or a dot for a shape with none. */
export function shapeGlyph(shape: string): string {
  return SHAPE_GLYPH[shape] ?? "●";
}

/** The CSS color drawn for `color`, or gray for a color with none. */
export function colorHex(color: string): string {
  return COLOR_HEX[color] ?? "#6b7280";
}
