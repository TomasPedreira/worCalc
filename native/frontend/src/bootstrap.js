import {invoke} from "@tauri-apps/api/core";
import {createNativeApi, nativeSketchStorage, nativeKillTracker} from "../transport.js";

if (!window.__TAURI_INTERNALS__) throw Error("Open worCalc as the installed Tauri application.");
if (import.meta.env.MODE === "kill-tracker") {
  globalThis.worcalcNative = {variant:"kill-tracker", killTracker:nativeKillTracker(invoke)};
  const {mountKillTracker} = await import("./kill-tracker.js");
  mountKillTracker(document, globalThis.worcalcNative.killTracker);
} else {
  globalThis.worcalcNative = {variant:import.meta.env.MODE === "sketcher" ? "sketcher" : "calculator", api:createNativeApi(invoke)};
  await import("./map-marker.js");
  await import("./fire-readout.js");
  await import("./artillery-positions.js");
  if (import.meta.env.MODE === "sketcher") {
    globalThis.worcalcNative.sketchStorage = nativeSketchStorage(invoke);
    await import("./sketch-model.js");
    await import("./sketcher.js");
  }
  await import("./app.js");
}
