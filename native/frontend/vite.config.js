import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import {readFileSync} from "node:fs";
import {appVariant, variantHtml} from "./app-variant.js";
const {version} = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8"));
export default defineConfig(({mode}) => ({
  root: fileURLToPath(new URL("./src", import.meta.url)),
  plugins:[{
    name:"worcalc-app-variant",
    transformIndexHtml:{order:"pre", handler:html => variantHtml(html, appVariant(mode))},
    generateBundle() {
      this.emitFile({type:"asset", fileName:"build-info.json", source:JSON.stringify({version, variant:appVariant(mode)})});
    },
  }],
  server: {port:1420,strictPort:true,host:"127.0.0.1"},
  build: {outDir:`../dist-${appVariant(mode)}`,emptyOutDir:true},
}));
