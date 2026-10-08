import {invoke} from "@tauri-apps/api/core";
import {createNativeApi, nativeSketchStorage} from "../transport.js";

if (!window.__TAURI_INTERNALS__) throw Error("Open worCalc as the installed Tauri application.");
globalThis.worcalcNative = {
  api:createNativeApi(invoke),
  sketchStorage:nativeSketchStorage(invoke),
};
await import("./map-marker.js");
await import("./fire-readout.js");
await import("./sketch-model.js");
await import("./sketcher.js");
await import("./app.js");
