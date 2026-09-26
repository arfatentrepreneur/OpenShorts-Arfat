import { before, test } from "node:test";
import assert from "node:assert/strict";
import { selectComposition } from "@remotion/renderer";
import { initBundle, getBundleLocation } from "./bundle.js";

/**
 * Contract test for the render pipeline's composition metadata.
 *
 * render-worker.ts passes durationInFrames/fps/width/height via inputProps and
 * renders whatever selectComposition() reports. Without calculateMetadata on
 * the ShortVideo Composition, Remotion ignores those inputProps and always
 * reports the static DEFAULT_PROPS metadata (900 frames / 30fps / 1080x1920),
 * so every clip renders at 30s regardless of its real length.
 */

const BUNDLE_TIMEOUT_MS = 5 * 60 * 1000;

before(async () => {
  await initBundle();
}, { timeout: BUNDLE_TIMEOUT_MS });

test(
  "selectComposition honors per-render duration/fps/dimensions from inputProps",
  { timeout: BUNDLE_TIMEOUT_MS },
  async () => {
    const composition = await selectComposition({
      serveUrl: getBundleLocation(),
      id: "ShortVideo",
      inputProps: {
        videoUrl: "",
        durationInFrames: 300,
        fps: 25,
        width: 720,
        height: 1280,
      },
      logLevel: "error",
    });

    assert.equal(composition.durationInFrames, 300);
    assert.equal(composition.fps, 25);
    assert.equal(composition.width, 720);
    assert.equal(composition.height, 1280);
  }
);

test(
  "selectComposition falls back to DEFAULT_PROPS metadata when inputProps omit it",
  { timeout: BUNDLE_TIMEOUT_MS },
  async () => {
    const composition = await selectComposition({
      serveUrl: getBundleLocation(),
      id: "ShortVideo",
      inputProps: { videoUrl: "" },
      logLevel: "error",
    });

    assert.equal(composition.durationInFrames, 900);
    assert.equal(composition.fps, 30);
    assert.equal(composition.width, 1080);
    assert.equal(composition.height, 1920);
  }
);
