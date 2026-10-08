/** Local Tauri commands. The application has no HTTP or browser fallback. */
async function callNative(invoke, command, args) {
  try {return await invoke(command, args);}
  catch (error) {throw error instanceof Error ? error : Error(String(error));}
}
export function nativeResources(invoke) {
  return async path => new Uint8Array(await callNative(invoke, "native_resource", {path}));
}
export function nativeSketchStorage(invoke) {
  return {
    load:() => callNative(invoke, "native_sketch", {operation:"load", data:null}),
    save:data => callNative(invoke, "native_sketch", {operation:"save", data}),
    export:async data => `Exported to ${await callNative(invoke, "native_sketch", {operation:"export", data})}`,
  };
}
export function createNativeApi(invoke) {
  const read = nativeResources(invoke);
  const request = (operation, data = null) => callNative(invoke, "native_request", {operation, data});
  return {
    maps:() => request("maps"),
    options:() => request("options"),
    locations:mapId => request("locations", {map_id:mapId}),
    calculate:mission => request("calculate", mission),
    recordImpact:impact => request("impact", impact),
    mapImage:async (path, signal) => {
      const checkAbort = () => {if (signal?.aborted) throw new DOMException("Aborted", "AbortError");};
      checkAbort();
      if (!/^maps\/map-\d+(?:-thumb)?\.webp$/.test(path)) throw Error("Invalid map resource");
      try {
        const bytes = await read(path);
        checkAbort();
        return new Blob([bytes], {type:"image/webp"});
      } catch (error) {
        checkAbort();
        throw error instanceof Error ? error : Error(String(error));
      }
    },
  };
}
