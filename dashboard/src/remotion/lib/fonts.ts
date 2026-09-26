import { staticFile } from "remotion";

/**
 * CSS @font-face declaration for NotoSerif-Bold (bundled locally).
 * Use in components via: <style>{notoSerifFontFace}</style>
 */
export const NOTO_SERIF_FONT_FAMILY = "NotoSerif-Bold";

export const notoSerifFontFace = `
@font-face {
  font-family: '${NOTO_SERIF_FONT_FAMILY}';
  src: url('${staticFile("fonts/NotoSerif-Bold.ttf")}') format('truetype');
  font-weight: 700;
  font-style: normal;
}
`;

/** Montserrat ExtraBold (bundled, SIL OFL): the "pill" hook style's sans. */
export const MONTSERRAT_FONT_FAMILY = "Montserrat-ExtraBold";

export const montserratFontFace = `
@font-face {
  font-family: '${MONTSERRAT_FONT_FAMILY}';
  src: url('${staticFile("fonts/Montserrat-ExtraBold.ttf")}') format('truetype');
  font-weight: 800;
  font-style: normal;
}
`;

/** Anton (bundled, SIL OFL): the condensed hook typeface. */
export const ANTON_FONT_FAMILY = "Anton-Regular";

export const antonFontFace = `
@font-face {
  font-family: '${ANTON_FONT_FAMILY}';
  src: url('${staticFile("fonts/Anton-Regular.ttf")}') format('truetype');
  font-weight: 400;
  font-style: normal;
}
`;

/**
 * Hook typefaces: CSS family + share of the 90% box width used as font size.
 * Must mirror hooks.py HOOK_FONTS.
 */
export const HOOK_FONTS: Record<string, { family: string; weight: number; factor: number }> = {
  montserrat: { family: `'${MONTSERRAT_FONT_FAMILY}', 'Montserrat', sans-serif`, weight: 800, factor: 0.064 },
  anton: { family: `'${ANTON_FONT_FAMILY}', Impact, sans-serif`, weight: 400, factor: 0.08 },
  serif: { family: `'${NOTO_SERIF_FONT_FAMILY}', 'Noto Serif', Georgia, serif`, weight: 700, factor: 0.05 },
};

/**
 * Map of subtitle font families to their CSS-safe names.
 * These match the options available in SubtitleModal.jsx.
 */
export const SUBTITLE_FONTS: Record<string, string> = {
  Verdana: "Verdana, Geneva, sans-serif",
  Arial: "Arial, Helvetica, sans-serif",
  Impact: "Impact, Haettenschweiler, sans-serif",
  Helvetica: "Helvetica, Arial, sans-serif",
  Georgia: "Georgia, 'Times New Roman', serif",
  "Courier New": "'Courier New', Courier, monospace",
};

export function getFontStack(fontFamily: string): string {
  return SUBTITLE_FONTS[fontFamily] ?? fontFamily;
}
