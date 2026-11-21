import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, mkdtemp, readdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'vite';
import {appVariant, variantHtml} from '../app-variant.js';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const readJson = async path => JSON.parse(await readFile(join(root,path), 'utf8'));

test('default application is the calculator; all three apps have independent identities', async () => {
  assert.equal(appVariant('production'), 'calculator');
  assert.equal(appVariant('sketcher'), 'sketcher');
  assert.equal(appVariant('kill-tracker'), 'kill-tracker');
  const apps = await readJson('native/apps.json');
  const base = await readJson('src-tauri/tauri.conf.json');
  const pkg = await readJson('package.json');
  assert.equal(base.version, pkg.version);
  assert.equal(new Set(Object.values(apps).map(app => app.identifier)).size,3);
  assert.equal(new Set(Object.values(apps).map(app => app.executable)).size,3);
  for (const [variant, app] of Object.entries(apps)) {
    const config = await readJson(app.config);
    assert.equal(config.identifier,app.identifier);
    assert.equal(config.productName,app.name);
    assert.equal(config.build.frontendDist,`../native/frontend/dist-${variant}`);
    if (!app.maps) assert.deepEqual(config.bundle.resources,[]);
  }
});

test('standalone pages have no hub, cross-app navigation or unrelated panels', async () => {
  const source = await readFile(join(root,'native/frontend/src/index.html'),'utf8');
  for (const variant of ['calculator','sketcher','kill-tracker']) {
    const html = variantHtml(source,variant);
    assert.doesNotMatch(html,/app-chooser|choose-app|choose-calculator|choose-sketcher|choose-kill-tracker|kill-tracker-back/);
    assert.match(html,new RegExp(`data-app-variant="${variant}"`));
    if (variant === 'kill-tracker') {
      assert.match(html,/id="kill-start"/);
      assert.doesNotMatch(html,/id="map-image"|id="sketch-panel"/);
    } else {
      assert.match(html,/id="map-image"/);
      assert.doesNotMatch(html,/id="kill-start"/);
      assert.equal(html.includes('id="sketch-panel"'),variant === 'sketcher');
    }
  }
});

test('production bundles omit the other applications and their native adapters', async () => {
  const temporary = await mkdtemp(join(tmpdir(),'worcalc-variants-'));
  try {
    for (const variant of ['calculator','sketcher','kill-tracker']) {
      const output = join(temporary,variant);
      await build({configFile:join(root,'native/frontend/vite.config.js'),mode:variant,logLevel:'silent',build:{outDir:output,emptyOutDir:true}});
      const info = JSON.parse(await readFile(join(output,'build-info.json'),'utf8'));
      assert.equal(info.variant,variant);
      const assets = await readdir(join(output,'assets'));
      const javascript = (await Promise.all(assets.filter(path=>path.endsWith('.js')).map(path=>readFile(join(output,'assets',path),'utf8')))).join('\n');
      if (variant === 'calculator') {
        assert.ok(!assets.some(path=>/sketch|kill-tracker/.test(path)));
        assert.doesNotMatch(javascript,/native_sketch|native_kill_tracker/);
      } else if (variant === 'sketcher') {
        assert.ok(assets.some(path=>path.startsWith('sketcher-')));
        assert.doesNotMatch(javascript,/native_kill_tracker/);
      } else {
        assert.ok(!assets.some(path=>/sketch|artillery-positions|map-marker|fire-readout|^app-/.test(path)));
        assert.doesNotMatch(javascript,/native_request|native_resource|native_sketch/);
      }
    }
  } finally {
    assert.equal(dirname(resolve(temporary)),resolve(tmpdir()));
    assert.ok(temporary.startsWith(join(tmpdir(),'worcalc-variants-')));
    await rm(temporary,{recursive:true,force:true});
  }
});
