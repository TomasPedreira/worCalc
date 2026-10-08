/** Validate and stage the offline data pack for Tauri. Requires only Node.js. */
import {readFile, mkdir, copyFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {resolve, dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

export function assetPaths(catalog) {
  if (catalog.version !== 1 || !Array.isArray(catalog.maps) || !catalog.maps.length) throw Error("Unsupported or empty map catalog");
  const paths = new Set(["catalog.json"]);
  const identifiers = new Set();
  for (const map of catalog.maps) {
    if (!/^map-\d+$/.test(map.identifier) || identifiers.has(map.identifier) ||
        !/^[A-Za-z0-9]+$/.test(map.battlefield) || !Number.isInteger(map.width_pixels) || !Number.isInteger(map.height_pixels) ||
        map.width_pixels <= 0 || map.height_pixels <= 0 || map.width_pixels > 16384 || map.height_pixels > 16384 ||
        map.image_path !== `maps/${map.identifier}.webp` || map.thumbnail_path !== `maps/${map.identifier}-thumb.webp`) {
      throw Error(`Invalid bundled map: ${map.identifier}`);
    }
    identifiers.add(map.identifier);
    paths.add(map.image_path); paths.add(map.thumbnail_path);
    paths.add(`terrain/${map.battlefield}.wrtz`);
  }
  return [...paths].sort();
}
const signature = bytes => ({size:bytes.length, sha256:createHash("sha256").update(bytes).digest("hex")});
export async function createManifest(directory) {
  const catalog = JSON.parse(await readFile(join(directory, "catalog.json"), "utf8"));
  const files = {};
  for (const path of assetPaths(catalog)) files[path] = signature(await readFile(join(directory, path)));
  return {version:1, files};
}
export async function validateAssetPack(directory) {
  let catalog, manifest;
  try {
    catalog = JSON.parse(await readFile(join(directory,"catalog.json"),"utf8"));
    manifest = JSON.parse(await readFile(join(directory,"manifest.json"),"utf8"));
  } catch (error) {throw Error(`Offline data pack is missing or unreadable at ${directory}. Restore native/assets from your data-pack backup. ${error.message}`);}
  const paths = assetPaths(catalog);
  if (manifest.version !== 1 || !manifest.files || JSON.stringify(Object.keys(manifest.files).sort()) !== JSON.stringify(paths)) {
    throw Error("The offline data manifest does not match the catalog");
  }
  for (const path of paths) {
    const actual = signature(await readFile(join(directory,path)));
    const expected = manifest.files[path];
    if (expected?.size !== actual.size || expected?.sha256 !== actual.sha256) throw Error(`Corrupt offline asset: ${path}`);
  }
  return {catalog, paths, manifest};
}
export async function prepareAssets(source, destination) {
  const {catalog,paths,manifest} = await validateAssetPack(source);
  for (const path of paths) {
    const output = join(destination,path);
    try {
      const existing = signature(await readFile(output));
      if (existing.size === manifest.files[path].size && existing.sha256 === manifest.files[path].sha256) continue;
    } catch (error) {if (error.code !== "ENOENT") throw error;}
    await mkdir(dirname(output),{recursive:true});
    await copyFile(join(source,path),output);
  }
  return {maps:catalog.maps.length, files:paths.length};
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = fileURLToPath(new URL("../",import.meta.url));
  const result = await prepareAssets(join(root,"native/assets"),join(root,"src-tauri/resources"));
  console.log(`Prepared ${result.maps} offline maps (${result.files} validated assets).`);
}
