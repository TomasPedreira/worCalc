import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp, mkdir, readFile, writeFile, rm, stat, utimes} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {fileURLToPath} from "node:url";
import {assetPaths, createManifest, validateAssetPack, prepareAssets} from "../../prepare-assets.js";

async function fixture(t) {
  const root=await mkdtemp(join(tmpdir(),"worcalc-assets-"));
  t.after(()=>rm(root,{recursive:true,force:true}));
  const source=join(root,"source");await mkdir(join(source,"maps"),{recursive:true});await mkdir(join(source,"terrain"));
  const catalog={version:1,maps:[{identifier:"map-1",battlefield:"Test",width_pixels:2,height_pixels:2,
    image_path:"maps/map-1.webp",thumbnail_path:"maps/map-1-thumb.webp"}]};
  await writeFile(join(source,"catalog.json"),JSON.stringify(catalog));
  for(const path of assetPaths(catalog).filter(path=>path!=="catalog.json")) await writeFile(join(source,path),new Uint8Array([0,128,255]));
  const manifest=await createManifest(source);await writeFile(join(source,"manifest.json"),JSON.stringify(manifest));
  return {root,source,catalog,manifest};
}
test("assets are prepared without Python and preserve every byte",async t=>{
  const f=await fixture(t), output=join(f.root,"bundled");
  assert.deepEqual(await prepareAssets(f.source,output),{maps:1,files:4});
  for(const path of assetPaths(f.catalog)) assert.deepEqual(await readFile(join(output,path)),await readFile(join(f.source,path)));
});
test("unchanged staged assets keep their timestamps and corrupted copies are repaired",async t=>{
  const f=await fixture(t),output=join(f.root,"bundled");await prepareAssets(f.source,output);
  const image=join(output,"maps/map-1.webp"),time=new Date("2020-01-01T00:00:00Z");
  await utimes(image,time,time);await prepareAssets(f.source,output);
  assert.equal((await stat(image)).mtimeMs,time.getTime());
  await writeFile(image,new Uint8Array([255,128,0]));await prepareAssets(f.source,output);
  assert.deepEqual(await readFile(image),await readFile(join(f.source,"maps/map-1.webp")));
});
test("corrupt or missing assets fail validation before staging",async t=>{
  const f=await fixture(t);await writeFile(join(f.source,"maps/map-1.webp"),"changed");
  await assert.rejects(prepareAssets(f.source,join(f.root,"out")),/Corrupt offline asset/);
  await assert.rejects(readFile(join(f.root,"out/catalog.json")),{code:"ENOENT"});
  await rm(join(f.source,"manifest.json"));await assert.rejects(validateAssetPack(f.source),/Restore native\/assets/);
});
test("catalog traversal, duplicate maps and mismatched manifests are rejected",async t=>{
  const f=await fixture(t);
  assert.throws(()=>assetPaths({...f.catalog,maps:[{...f.catalog.maps[0],battlefield:"../Test"}]}),/Invalid bundled map/);
  assert.throws(()=>assetPaths({...f.catalog,maps:[...f.catalog.maps,...f.catalog.maps]}),/Invalid bundled map/);
  f.manifest.files["../outside"]=Object.values(f.manifest.files)[0];
  await writeFile(join(f.source,"manifest.json"),JSON.stringify(f.manifest));
  await assert.rejects(validateAssetPack(f.source),/manifest does not match/);
});
test("the real offline pack contains 99 maps, 198 images and four terrains",async()=>{
  const pack=await validateAssetPack(fileURLToPath(new URL("../../assets",import.meta.url)));
  assert.equal(pack.catalog.maps.length,99);
  assert.equal(pack.paths.filter(path=>path.startsWith("maps/")).length,198);
  assert.equal(pack.paths.filter(path=>path.startsWith("terrain/")).length,4);
});
