const $ = (selector) => document.querySelector(selector);
const mapWrap = $("#map-wrap");
const scene = $("#scene");
const mapImage = $("#map-image");
const gunAnchor = $("#gun-anchor");
const targetAnchor = $("#target-anchor");
const shotLine = $("#shot-line");
const rangeChip = $("#range-chip");
const modePill = $("#mode-pill");
const drawer = $("#drawer");
const sheet = $("#sheet");
const backdrop = $("#backdrop");
const MAX_ZOOM = 12;

let maps = [];
let options = null;
let currentMap = null;
let mapReady = false;
let locations = [];
let locationAnchors = [];
let mode = "pan";
let zoom = 1;
let translateX = 0;
let translateY = 0;
let baseScale = 1;
let sceneWidth = 1;
let sceneHeight = 1;
let gun = null;
let target = null;
let latestSolution = null;
let impacts = [];
let expandedBattlefield = null;
const expandedModes = new Map();
let solutionRequestSequence = 0;
let thumbnailPrefetchController = null;
let mapImageRequestSequence = 0;
let displayedImageRequestSequence = 0;
let mapImageFetchController = null;
let currentMapObjectUrl = null;
const thumbnailObjectUrls = new Map();
const thumbnailLoads = new Map();

const pointers = new Map();
let primaryPointerId = null;
let pointerStart = null;
let startTranslation = null;
let dragged = false;
let draggingMarker = null;
let markerMoveStarted = false;
let pendingPlacement = null;
let pinching = false;
let pinchStartDistance = 0;
let pinchStartZoom = 1;
let pinchAnchorX = 0;
let pinchAnchorY = 0;

function addOptions(select, values) {
  select.replaceChildren(...values.map((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    return option;
  }));
}

function clampTranslation() {
  const rect = mapWrap.getBoundingClientRect();
  const scaledWidth = sceneWidth * zoom;
  const scaledHeight = sceneHeight * zoom;
  // Allow dragging at fit zoom too; retain a visible strip for recovery.
  const visibleX = Math.min(64, rect.width / 4, scaledWidth / 4);
  const visibleY = Math.min(64, rect.height / 4, scaledHeight / 4);
  translateX = Math.max(visibleX-scaledWidth, Math.min(rect.width-visibleX, translateX));
  translateY = Math.max(visibleY-scaledHeight, Math.min(rect.height-visibleY, translateY));
}

function applyView() {
  clampTranslation();
  scene.style.setProperty("--inverse-zoom", String(1 / zoom));
  scene.style.transform = `translate(${translateX}px,${translateY}px) scale(${zoom})`;
  updateMarkerPositions();
  updateLocationPositions();
  updateRangeChipPosition();
}

function resetView() {
  if (!mapImage.naturalWidth) return;
  const rect = mapWrap.getBoundingClientRect();
  baseScale = Math.min(rect.width / mapImage.naturalWidth, rect.height / mapImage.naturalHeight);
  sceneWidth = mapImage.naturalWidth * baseScale;
  sceneHeight = mapImage.naturalHeight * baseScale;
  scene.style.width = `${sceneWidth}px`;
  scene.style.height = `${sceneHeight}px`;
  zoom = 1;
  translateX = (rect.width - sceneWidth) / 2;
  translateY = (rect.height - sceneHeight) / 2;
  renderLocations();
  renderImpacts();
  updateMissionGeometry();
  applyView();
}

function imagePoint(clientX, clientY) {
  const rect = mapWrap.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(mapImage.naturalWidth, (clientX - rect.left - translateX) / zoom / baseScale)),
    y: Math.max(0, Math.min(mapImage.naturalHeight, (clientY - rect.top - translateY) / zoom / baseScale)),
  };
}

function screenPoint(point) {
  return {
    x: translateX + point.x * baseScale * zoom,
    y: translateY + point.y * baseScale * zoom,
  };
}

function setAnchor(anchor, point) {
  const screen = screenPoint(point);
  anchor.style.left = `${screen.x}px`;
  anchor.style.top = `${screen.y}px`;
  anchor.hidden = false;
}

function updateMarkerPositions() {
  if (gun) setAnchor(gunAnchor, gun);
  if (target) setAnchor(targetAnchor, target);
}

function updateLocationPositions() {
  locationAnchors.forEach((anchor, index) => {
    const location = locations[index];
    if (!location) return;
    const screen = screenPoint({x:location.pixel_x, y:location.pixel_y});
    anchor.style.left = `${screen.x}px`;
    anchor.style.top = `${screen.y}px`;
  });
}

function updateRangeChipPosition() {
  if (!gun || !target) return;
  const first = screenPoint(gun);
  const second = screenPoint(target);
  const rect = mapWrap.getBoundingClientRect();
  const width = rangeChip.offsetWidth || 190;
  const height = rangeChip.offsetHeight || 54;
  // Prefer the side beyond the target, away from the gun-to-target segment.
  const xs = [second.x+24, second.x-width-24];
  const ys = [second.y+24, second.y-height-24];
  if (second.x < first.x) xs.reverse();
  if (second.y < first.y) ys.reverse();
  const candidates = xs.flatMap(x => ys.map(y => ({
    x:Math.max(8, Math.min(rect.width-width-8, x)),
    y:Math.max(8, Math.min(rect.height-height-64, y)),
  })));
  const crossesFlight = box => {
    let low=0, high=1;
    for (const [start, delta, min, max] of [
      [first.x,second.x-first.x,box.x-8,box.x+width+8],
      [first.y,second.y-first.y,box.y-8,box.y+height+8],
    ]) {
      if (delta === 0) { if (start<min || start>max) return false; }
      else {
        const a=(min-start)/delta, b=(max-start)/delta;
        low=Math.max(low,Math.min(a,b)); high=Math.min(high,Math.max(a,b));
        if (low>high) return false;
      }
    }
    return true;
  };
  const position = candidates.find(box => !crossesFlight(box)) || candidates[0];
  rangeChip.style.left = `${position.x}px`;
  rangeChip.style.top = `${position.y}px`;
}

function updateMissionGeometry() {
  if (gun) setAnchor(gunAnchor, gun);
  if (target) setAnchor(targetAnchor, target);
  if (!gun || !target) {
    shotLine.hidden = true;
    rangeChip.hidden = true;
    return;
  }
  const gx = gun.x * baseScale;
  const gy = gun.y * baseScale;
  const tx = target.x * baseScale;
  const ty = target.y * baseScale;
  const dx = tx - gx;
  const dy = ty - gy;
  shotLine.style.left = `${gx}px`;
  shotLine.style.top = `${gy}px`;
  shotLine.style.width = `${Math.hypot(dx, dy)}px`;
  shotLine.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
  shotLine.hidden = false;
  rangeChip.hidden = !latestSolution;
  updateRangeChipPosition();
}

function cancelPendingSolution() {
  solutionRequestSequence += 1;
  mapWrap.classList.remove("solution-loading");
  if (!mapWrap.classList.contains("map-loading")) setMode(mode);
}

function clearSolution() {
  cancelPendingSolution();
  latestSolution = null;
  impacts = [];
  renderImpacts();
  for (const id of ["elevation", "fuze"]) {
    $(`#${id}`).textContent = "—";
  }
  rangeChip.hidden = true;
  $("#distance").textContent = "—";
  $("#height").textContent = "—";
  $("#explosion-height").textContent = "—";
  shotLine.classList.remove("clear", "obstructed");
  updateMissionGeometry();
}

function clearMission(resetMap = true) {
  gun = null;
  target = null;
  gunAnchor.hidden = true;
  targetAnchor.hidden = true;
  shotLine.hidden = true;
  rangeChip.hidden = true;
  clearSolution();
  if (resetMap) resetView();
  setMode("pan");
}

function setMode(nextMode) {
  mode = nextMode;
  $("#gun-mode").classList.toggle("active", mode === "gun");
  $("#target-mode").classList.toggle("active", mode === "target");
  $("#impact-mode").classList.toggle("active", mode === "impact");
  modePill.textContent = mode === "pan"
    ? "HOLD & DRAG TO PAN"
    : mode === "gun" ? "CLICK MAP TO PLACE GUN" : mode === "impact"
      ? "CLICK WHERE THE SHOT LANDED" : "CLICK MAP TO PLACE TARGET";
}

function calibrationMode() {
  return $("#calculation-mode").value === "test";
}

function airburstMode() {
  return $("#burst-mode").value === "airburst";
}

function updateCalculationMode() {
  const enabled = calibrationMode();
  $("#impact-mode").hidden = !enabled;
  $("#calibration-angle-field").hidden = !enabled;
  $("#calibration-help").hidden = !enabled;
  if (!enabled && mode === "impact") setMode("pan");
}

function renderImpacts() {
  $("#impact-layer").replaceChildren(...impacts.map((point, index) => {
    const marker = document.createElement("span");
    marker.className = "impact-mark";
    marker.style.left = `${point.x * baseScale}px`;
    marker.style.top = `${point.y * baseScale}px`;
    marker.textContent = `×${index+1}`;
    marker.title = "Observed impact saved to shot log";
    return marker;
  }));
}

async function markImpact(clientX, clientY, exactPoint = null) {
  if (!calibrationMode()) {
    modePill.textContent = "SWITCH TO CALIBRATION TEST TO RECORD IMPACTS";
    return;
  }
  if (!mapReady || !latestSolution?.calculation_id) {
    modePill.textContent = "CALCULATE A SHOT BEFORE MARKING IMPACT";
    return;
  }
  const actualElevation = Number($("#actual-elevation").value);
  if (!Number.isFinite(actualElevation) || $("#actual-elevation").value.trim() === "") {
    modePill.textContent = "ENTER THE ACTUAL ELEVATION FIRED";
    $("#actual-elevation").focus();
    return;
  }
  const shotId = latestSolution.calculation_id;
  const point = exactPoint || imagePoint(clientX, clientY);
  modePill.textContent = "SAVING IMPACT...";
  try {
    const response = await fetch("/api/impacts", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({calculation_id:shotId, impact:point,
                           actual_elevation_degrees:actualElevation})});
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || "Impact could not be saved");
    if (latestSolution?.calculation_id !== shotId) return;
    impacts.push(point);
    renderImpacts();
    modePill.textContent = `IMPACT ${impacts.length} SAVED`;
  } catch (error) {
    if (latestSolution?.calculation_id === shotId) modePill.textContent = error.message;
  }
}

function moveMarker(name, clientX, clientY) {
  clearSolution();
  const point = imagePoint(clientX, clientY);
  if (name === "gun") gun = point;
  else target = point;
  updateMissionGeometry();
}

function locationClass(location) {
  return `${location.kind} ${(location.faction || "").toLowerCase()}`;
}

function battlefieldLabel(name) {
  return name.replace(/([a-z])([A-Z])/g, "$1 $2");
}

function createMapCard(map, loadThumbnail) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `map-card${map.identifier === currentMap?.identifier ? " active" : ""}`;
  const image = document.createElement("img");
  if (loadThumbnail) loadThumbnailInto(image, map);
  image.alt = "";
  image.loading = "lazy";
  const copy = document.createElement("div");
  const name = document.createElement("b");
  name.textContent = map.name;
  const detail = document.createElement("small");
  detail.textContent = `Area ${String(map.gameplay_area + 1).padStart(2, "0")}`;
  copy.append(name, detail);
  button.append(image, copy);
  button.addEventListener("click", () => {
    selectMap(map);
    closePanels();
  });
  return button;
}

async function thumbnailObjectUrl(map, signal = undefined) {
  if (thumbnailObjectUrls.has(map.identifier)) {
    return thumbnailObjectUrls.get(map.identifier);
  }
  if (thumbnailLoads.has(map.identifier)) {
    return thumbnailLoads.get(map.identifier);
  }
  const load = (async () => {
    const response = await fetch(map.thumbnail_url, {signal, cache:"no-store"});
    if (!response.ok) throw new Error(`Could not load thumbnail: ${map.name}`);
    const objectUrl = URL.createObjectURL(await response.blob());
    thumbnailObjectUrls.set(map.identifier, objectUrl);
    return objectUrl;
  })();
  thumbnailLoads.set(map.identifier, load);
  try {
    return await load;
  } finally {
    if (thumbnailLoads.get(map.identifier) === load) {
      thumbnailLoads.delete(map.identifier);
    }
  }
}

async function loadThumbnailInto(image, map) {
  try {
    const objectUrl = await thumbnailObjectUrl(map);
    if (image.isConnected) image.src = objectUrl;
  } catch (error) {
    if (error.name !== "AbortError") {
      console.warn("Thumbnail load failed", error);
      return;
    }
    try {
      const objectUrl = await thumbnailObjectUrl(map);
      if (image.isConnected) image.src = objectUrl;
    } catch (retryError) {
      if (retryError.name !== "AbortError") console.warn("Thumbnail load failed", retryError);
    }
  }
}

function cancelThumbnailPrefetch() {
  thumbnailPrefetchController?.abort();
  thumbnailPrefetchController = null;
}

async function prefetchSkirmishThumbnails(battlefield) {
  cancelThumbnailPrefetch();
  const skirmishMaps = maps.filter((map) =>
    map.battlefield === battlefield && map.mode.toLowerCase() === "skirmish");
  if (!skirmishMaps.length) return;
  const controller = new AbortController();
  thumbnailPrefetchController = controller;
  try {
    for (const map of skirmishMaps) {
      await thumbnailObjectUrl(map, controller.signal);
    }
  } catch (error) {
    if (error.name !== "AbortError") console.warn("Thumbnail prefetch failed", error);
  } finally {
    if (thumbnailPrefetchController === controller) thumbnailPrefetchController = null;
  }
}

function renderLocations() {
  const layer = $("#location-layer");
  locationAnchors = locations.map((location) => {
    const anchor = document.createElement("span");
    anchor.className = "location-anchor";
    const dot = document.createElement("i");
    dot.className = `location-dot ${locationClass(location)}`;
    dot.textContent = location.kind === "gun_spawn" ? "G" : location.kind === "battery" ? "B" : location.kind === "objective" ? "P" : "S";
    const label = location.kind === "gun_spawn" ? "Gun starting position (before movement)"
      : location.kind === "battery" ? "Artillery crew spawn reference" : location.kind;
    dot.title = [location.faction, label, location.name].filter(Boolean).join(" · ");
    anchor.append(dot);
    return anchor;
  });
  updateLocationPositions();
  layer.replaceChildren(...locationAnchors);
}

function renderMapList(filter = "") {
  const term = filter.trim().toLowerCase();
  const filtered = maps.filter((map) =>
    `${map.battlefield} ${map.mode} ${map.name}`.toLowerCase().includes(term));
  const grouped = new Map();
  for (const map of filtered) {
    if (!grouped.has(map.battlefield)) grouped.set(map.battlefield, []);
    grouped.get(map.battlefield).push(map);
  }
  $("#map-list").replaceChildren(...Array.from(grouped, ([battlefield, variants]) => {
    const group = document.createElement("section");
    group.className = "map-group";
    const expanded = term ? true : battlefield === expandedBattlefield;
    const heading = document.createElement("h3");
    heading.className = "map-group-title";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "map-group-toggle";
    toggle.setAttribute("aria-expanded", String(expanded));
    const groupName = document.createElement("span");
    groupName.textContent = battlefieldLabel(battlefield);
    const groupMeta = document.createElement("span");
    groupMeta.className = "map-group-meta";
    groupMeta.textContent = `${variants.length} maps`;
    const chevron = document.createElement("span");
    chevron.className = "map-group-chevron";
    chevron.textContent = "⌄";
    toggle.append(groupName, groupMeta, chevron);
    toggle.addEventListener("click", () => {
      const nextBattlefield = expandedBattlefield === battlefield ? null : battlefield;
      cancelThumbnailPrefetch();
      expandedBattlefield = nextBattlefield;
      if (nextBattlefield) expandedModes.delete(nextBattlefield);
      renderMapList($("#map-search").value);
      if (nextBattlefield) prefetchSkirmishThumbnails(nextBattlefield);
    });
    heading.append(toggle);
    const modes = new Map();
    for (const map of variants) {
      if (!modes.has(map.mode)) modes.set(map.mode, []);
      modes.get(map.mode).push(map);
    }
    const modeGroups = document.createElement("div");
    modeGroups.className = "mode-groups";
    modeGroups.hidden = !expanded;
    modeGroups.append(...Array.from(modes, ([gameMode, modeMaps]) => {
      const modeGroup = document.createElement("section");
      modeGroup.className = "mode-group";
      const modeExpanded = term ? true : expandedModes.get(battlefield) === gameMode;
      const modeHeading = document.createElement("h4");
      modeHeading.className = "mode-group-title";
      const modeToggle = document.createElement("button");
      modeToggle.type = "button";
      modeToggle.className = "mode-group-toggle";
      modeToggle.setAttribute("aria-expanded", String(modeExpanded));
      const modeName = document.createElement("span");
      modeName.textContent = gameMode;
      const modeMeta = document.createElement("span");
      modeMeta.className = "mode-group-meta";
      modeMeta.textContent = String(modeMaps.length);
      const modeChevron = document.createElement("span");
      modeChevron.className = "mode-group-chevron";
      modeChevron.textContent = "⌄";
      modeToggle.append(modeName, modeMeta, modeChevron);
      modeToggle.addEventListener("click", () => {
        if (expandedModes.get(battlefield) === gameMode) expandedModes.delete(battlefield);
        else {
          expandedModes.set(battlefield, gameMode);
          if (gameMode.toLowerCase() !== "skirmish") cancelThumbnailPrefetch();
        }
        renderMapList($("#map-search").value);
      });
      modeHeading.append(modeToggle);
      const mapCards = document.createElement("div");
      mapCards.className = "map-variants";
      mapCards.hidden = !modeExpanded;
      mapCards.append(...modeMaps.map((map) => createMapCard(map, modeExpanded)));
      modeGroup.append(modeHeading, mapCards);
      return modeGroup;
    }));
    group.append(heading, modeGroups);
    return group;
  }));
}

async function selectMap(map) {
  cancelThumbnailPrefetch();
  mapReady = false;
  pointers.clear();
  primaryPointerId = null;
  pendingPlacement = null;
  draggingMarker = null;
  pinching = false;
  currentMap = map;
  $("#map-name").textContent = map.name;
  $("#map-subtitle").textContent = `${map.battlefield.toUpperCase()} / ${map.mode.toUpperCase()} / AREA ${String(map.gameplay_area + 1).padStart(2, "0")}`;
  locations = [];
  renderLocations();
  clearMission(false);
  loadMapImage(map);
  renderMapList($("#map-search").value);
  try {
    const response = await fetch(`/api/maps/${encodeURIComponent(map.identifier)}/locations`);
    if (!response.ok) throw new Error("Could not load map markers");
    const result = await response.json();
    if (currentMap?.identifier === map.identifier) {
      locations = result;
      renderLocations();
    }
  } catch (error) {
    modePill.textContent = error.message.toUpperCase();
  }
}

async function loadMapImage(map) {
  mapReady = false;
  const requestId = ++mapImageRequestSequence;
  mapImageFetchController?.abort();
  const controller = new AbortController();
  mapImageFetchController = controller;
  mapWrap.classList.add("map-loading");
  modePill.textContent = "LOADING SELECTED MAP...";
  try {
    const response = await fetch(map.image_url, {
      signal: controller.signal,
      cache:"no-store",
    });
    if (!response.ok) throw new Error("Selected map failed to load");
    const objectUrl = URL.createObjectURL(await response.blob());
    if (requestId !== mapImageRequestSequence || currentMap?.identifier !== map.identifier) {
      URL.revokeObjectURL(objectUrl);
      return;
    }
    const preloader = new Image();
    preloader.addEventListener("load", () => {
      if (requestId !== mapImageRequestSequence || currentMap?.identifier !== map.identifier) {
        URL.revokeObjectURL(objectUrl);
        return;
      }
      const previousObjectUrl = currentMapObjectUrl;
      currentMapObjectUrl = objectUrl;
      displayedImageRequestSequence = requestId;
      mapImage.src = objectUrl;
      if (previousObjectUrl) URL.revokeObjectURL(previousObjectUrl);
    });
    preloader.addEventListener("error", () => {
      URL.revokeObjectURL(objectUrl);
      if (requestId !== mapImageRequestSequence || currentMap?.identifier !== map.identifier) return;
      mapWrap.classList.remove("map-loading");
      mapImageFetchController = null;
      modePill.textContent = "SELECTED MAP FAILED TO LOAD";
    });
    preloader.src = objectUrl;
  } catch (error) {
    if (error.name === "AbortError") return;
    if (requestId !== mapImageRequestSequence || currentMap?.identifier !== map.identifier) return;
    mapWrap.classList.remove("map-loading");
    mapImageFetchController = null;
    modePill.textContent = "SELECTED MAP FAILED TO LOAD";
  }
}

function updatePhysics() {
  const cannon = $("#cannon-select").value;
  const projectile = $("#projectile-select").value;
  const profile = options.physics[cannon][projectile];
  $("#muzzle-velocity").value = `${profile.speed} m/s`;
  $("#drag-factor").value = `${profile.drag} s⁻¹`;
  clearSolution();
  if (gun && target && currentMap) requestSolution();
}

function refreshProjectiles(preferred = null) {
  const cannon = $("#cannon-select").value;
  const projectiles = options.weapons[cannon] || [];
  addOptions($("#projectile-select"), projectiles);
  if (preferred && projectiles.includes(preferred)) $("#projectile-select").value = preferred;
  updatePhysics();
}

async function load() {
  try {
    const [mapsResponse, optionsResponse] = await Promise.all([fetch("/api/maps"), fetch("/api/options")]);
    if (!mapsResponse.ok || !optionsResponse.ok) throw new Error("Could not load server data");
    maps = await mapsResponse.json();
    options = await optionsResponse.json();
    addOptions($("#cannon-select"), Object.keys(options.weapons));
    addOptions($("#method-select"), options.methods);
    $("#cannon-select").value = options.defaults.cannon;
    refreshProjectiles(options.defaults.projectile);
    $("#method-select").value = options.defaults.method;
    $("#calculation-mode").value = "operational";
    $("#burst-mode").value = "ground";
    updateCalculationMode();
    renderMapList();
    if (maps.length) selectMap(maps[0]);
    else $("#map-name").textContent = "No maps found";
  } catch (error) {
    $("#map-name").textContent = error.message;
  }
}

function openPanel(panel) {
  drawer.classList.toggle("open", panel === drawer);
  sheet.classList.toggle("open", panel === sheet);
  backdrop.classList.add("show");
}

function closePanels() {
  drawer.classList.remove("open");
  sheet.classList.remove("open");
  backdrop.classList.remove("show");
}

function getTwoPointers() { return Array.from(pointers.values()).slice(0, 2); }
function pointerDistance(first, second) { return Math.hypot(second.x - first.x, second.y - first.y); }
function pointerMidpoint(first, second) { return {x:(first.x + second.x) / 2, y:(first.y + second.y) / 2}; }

function beginPinch() {
  const pair = getTwoPointers();
  if (pair.length < 2) return;
  const midpoint = pointerMidpoint(pair[0], pair[1]);
  const rect = mapWrap.getBoundingClientRect();
  pinching = true;
  pinchStartDistance = Math.max(1, pointerDistance(pair[0], pair[1]));
  pinchStartZoom = zoom;
  pinchAnchorX = (midpoint.x - rect.left - translateX) / zoom;
  pinchAnchorY = (midpoint.y - rect.top - translateY) / zoom;
  primaryPointerId = null;
  pointerStart = null;
  startTranslation = null;
  dragged = false;
  draggingMarker = null;
  markerMoveStarted = false;
  pendingPlacement = null;
}

function rebaseRemainingPointer() {
  const remaining = pointers.entries().next();
  if (remaining.done) return;
  const [pointerId, point] = remaining.value;
  primaryPointerId = pointerId;
  pointerStart = {x:point.x, y:point.y};
  startTranslation = {x:translateX, y:translateY};
  dragged = false;
  draggingMarker = null;
  markerMoveStarted = false;
  pendingPlacement = null;
}

function updatePinch() {
  const pair = getTwoPointers();
  if (!pinching || pair.length < 2) return;
  const midpoint = pointerMidpoint(pair[0], pair[1]);
  const rect = mapWrap.getBoundingClientRect();
  zoom = Math.max(1, Math.min(MAX_ZOOM, pinchStartZoom * pointerDistance(pair[0], pair[1]) / pinchStartDistance));
  translateX = midpoint.x - rect.left - pinchAnchorX * zoom;
  translateY = midpoint.y - rect.top - pinchAnchorY * zoom;
  applyView();
}

mapWrap.addEventListener("pointerdown", (event) => {
  if (event.button === 1) {
    event.preventDefault();
    const targetMarker = event.target?.closest?.('[data-marker="target"]');
    markImpact(event.clientX, event.clientY, targetMarker ? target : null);
    return;
  }
  if (event.button != null && event.button !== 0) return;
  if (!mapReady) return;
  if (event.target.closest("button,.map-name,.mode-pill,.status-bar,.range-chip")) return;
  mapWrap.setPointerCapture(event.pointerId);
  pointers.set(event.pointerId, {x:event.clientX, y:event.clientY});
  if (pointers.size === 2) { beginPinch(); return; }
  if (pointers.size > 2) return;
  primaryPointerId = event.pointerId;
  pointerStart = {x:event.clientX, y:event.clientY};
  startTranslation = {x:translateX, y:translateY};
  dragged = false;
  const marker = event.target.closest("[data-marker]");
  draggingMarker = marker?.dataset.marker || null;
  markerMoveStarted = false;
  pendingPlacement = marker ? null : (["gun", "target", "impact"].includes(mode) ? mode : null);
});

mapWrap.addEventListener("pointermove", (event) => {
  if (!pointers.has(event.pointerId)) return;
  pointers.set(event.pointerId, {x:event.clientX, y:event.clientY});
  if (pointers.size >= 2) { if (!pinching) beginPinch(); updatePinch(); return; }
  if (event.pointerId !== primaryPointerId || !pointerStart) return;
  const dx = event.clientX - pointerStart.x;
  const dy = event.clientY - pointerStart.y;
  if (Math.hypot(dx, dy) > 4) dragged = true;
  if (draggingMarker && dragged) {
    if (!markerMoveStarted) {
      cancelPendingSolution();
      markerMoveStarted = true;
    }
    moveMarker(draggingMarker, event.clientX, event.clientY);
  }
  else if (dragged) {
    translateX = startTranslation.x + dx;
    translateY = startTranslation.y + dy;
    applyView();
  }
});

function endPointer(event) {
  if (!mapReady) return;
  const wasPinching = pinching;
  pointers.delete(event.pointerId);
  if (wasPinching && pointers.size < 2) {
    pinching = false;
    if (pointers.size === 1) rebaseRemainingPointer();
    return;
  }
  if (event.pointerId === primaryPointerId) {
    let shouldRequestSolution = draggingMarker && markerMoveStarted;
    if (pendingPlacement && !dragged) {
      if (pendingPlacement === "impact") {
        markImpact(event.clientX, event.clientY);
      } else {
        cancelPendingSolution();
        moveMarker(pendingPlacement, event.clientX, event.clientY);
        shouldRequestSolution = true;
      }
      setMode("pan");
    }
    primaryPointerId = null;
    pointerStart = null;
    startTranslation = null;
    draggingMarker = null;
    markerMoveStarted = false;
    pendingPlacement = null;
    dragged = false;
    if (shouldRequestSolution && gun && target) requestSolution();
  }
}

mapWrap.addEventListener("pointerup", endPointer);
mapWrap.addEventListener("auxclick", event => { if (event.button === 1) event.preventDefault(); });
mapWrap.addEventListener("wheel", event => {
  if (!mapReady) return;
  event.preventDefault();
  const rect = mapWrap.getBoundingClientRect();
  const x = event.clientX-rect.left, y = event.clientY-rect.top;
  const next = Math.max(1, Math.min(MAX_ZOOM, zoom*Math.exp(-event.deltaY*0.0015)));
  translateX = x-(x-translateX)*next/zoom;
  translateY = y-(y-translateY)*next/zoom;
  zoom = next;
  applyView();
}, {passive:false});
window.addEventListener("keydown", event => {
  if (event.target?.closest("input,select,textarea") || event.ctrlKey || event.metaKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === "g") setMode("gun");
  if (key === "t") setMode("target");
  if (key === "i" && calibrationMode()) setMode("impact");
  if (key === "escape") { setMode("pan"); closePanels(); }
  if (key === "f") resetView();
});
mapWrap.addEventListener("pointercancel", endPointer);
mapImage.addEventListener("load", () => {
  if (displayedImageRequestSequence !== mapImageRequestSequence || mapImage.src !== currentMapObjectUrl) return;
  // The displayed image must be ready before coordinates can be selected.
  resetView();
  mapReady = true;
  mapWrap.classList.remove("map-loading");
  mapImageFetchController = null;
  setMode(mode);
});
$("#gun-mode").addEventListener("click", () => setMode(mode === "gun" ? "pan" : "gun"));
$("#target-mode").addEventListener("click", () => setMode(mode === "target" ? "pan" : "target"));
$("#impact-mode").addEventListener("click", () => setMode(mode === "impact" ? "pan" : "impact"));
$("#fit-map").addEventListener("click", resetView);
$("#open-drawer").addEventListener("click", () => openPanel(drawer));
$("#open-sheet").addEventListener("click", () => openPanel(sheet));
backdrop.addEventListener("click", closePanels);
document.querySelectorAll(".close").forEach((button) => button.addEventListener("click", closePanels));
$("#map-search").addEventListener("input", (event) => {
  cancelThumbnailPrefetch();
  renderMapList(event.target.value);
});
$("#cannon-select").addEventListener("change", () => refreshProjectiles());
$("#projectile-select").addEventListener("change", updatePhysics);
$("#method-select").addEventListener("change", () => {
  clearSolution();
  if (gun && target && currentMap) requestSolution();
});
$("#calculation-mode").addEventListener("change", () => {
  updateCalculationMode();
  clearSolution();
  if (gun && target && currentMap) requestSolution();
});
$("#burst-mode").addEventListener("change", () => {
  clearSolution();
  if (gun && target && currentMap) requestSolution();
});

async function requestSolution() {
  if (!gun || !target || !currentMap || !mapReady) return;
  clearSolution();
  const requestId = ++solutionRequestSequence;
  const requestedGun = {...gun};
  const requestedTarget = {...target};
  let succeeded = false;
  mapWrap.classList.add("solution-loading");
  modePill.textContent = "CALCULATING FIRE SOLUTION...";
  updateMissionGeometry();
  try {
    const response = await fetch("/api/solutions", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        map_id:currentMap.identifier,
        gun:requestedGun,
        target:requestedTarget,
        cannon:$("#cannon-select").value,
        projectile:$("#projectile-select").value,
        method:$("#method-select").value,
        calibration_mode:calibrationMode(),
        airburst_mode:airburstMode(),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Calculation failed");
    if (requestId !== solutionRequestSequence) return;
    latestSolution = data;
    $("#actual-elevation").value = data.elevation_degrees == null
      ? "" : (Math.round(data.elevation_degrees * 100) / 100).toFixed(2);
    $("#distance").textContent = `${data.slant_range_yards.toFixed(0)} yd`;
    $("#height").textContent = data.height_difference_metres == null ? "N/A" : `${data.height_difference_metres.toFixed(1)} m`;
    $("#elevation").textContent = data.elevation_degrees == null
      ? "No solution" : `${data.elevation_degrees.toFixed(2)}°`;
    $("#elevation-label").textContent = data.elevation_source === "calibration_test"
      ? "TEST ELEVATION" : data.elevation_source === "terrain_clearance"
        ? "CLEARANCE" : "ELEVATION";
    $("#fuze").textContent = data.fuze_seconds == null ? "—" : `${data.fuze_seconds.toFixed(3)} s`;
    $("#explosion-height").textContent = data.height_above_target_metres == null
      ? "N/A"
      : `${data.height_above_target_metres >= 0 ? "+" : ""}${data.height_above_target_metres.toFixed(1)} m`;
    shotLine.classList.toggle("clear", data.clearance_status === "clear");
    shotLine.classList.remove("obstructed");
    succeeded = true;
    updateMissionGeometry();
  } catch (error) {
    if (requestId === solutionRequestSequence) modePill.textContent = error.message.toUpperCase();
  } finally {
    if (requestId === solutionRequestSequence) {
      mapWrap.classList.remove("solution-loading");
      if (succeeded) setMode(mode);
      if (succeeded && latestSolution?.elevation_degrees == null) {
        modePill.textContent = "NO SOLUTION FOR THIS RANGE AND HEIGHT";
      }
      updateMissionGeometry();
    }
  }
}

window.addEventListener("resize", resetView);
window.addEventListener("beforeunload", () => {
  thumbnailPrefetchController?.abort();
  mapImageFetchController?.abort();
  for (const objectUrl of thumbnailObjectUrls.values()) URL.revokeObjectURL(objectUrl);
  if (currentMapObjectUrl) URL.revokeObjectURL(currentMapObjectUrl);
});
load();
