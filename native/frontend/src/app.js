const nativeApi = globalThis.worcalcNative.api;
const $ = (selector) => document.querySelector(selector);
const mapWrap = $("#map-wrap");
const scene = $("#scene");
const mapImage = $("#map-image");
const gunAnchor = $("#gun-anchor");
const targetAnchor = $("#target-anchor");
gunAnchor.replaceChildren(globalThis.WorCalcMapMarkers.create("gun"));
targetAnchor.replaceChildren(globalThis.WorCalcMapMarkers.create("target"));
const shotLine = $("#shot-line");
const aimOverlay = $("#aim-overlay");
const rangeChip = $("#range-chip");
rangeChip.replaceChildren(...globalThis.WorCalcFireReadouts.create({ids:{elevationLabel:"elevation-label", elevation:"elevation", fuze:"fuze"}}).children);
const modePill = $("#mode-pill");
function showStatus(message) {
  modePill.classList.remove("idle-hint");
  modePill.textContent = message;
}
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
let locationsReady = false;
let showArtilleryNames = true;
let sketcher = null;
let applicationMode = globalThis.worcalcNative.variant || "calculator";
const supportsMultipleTargets = applicationMode === "calculator" && /\bWindows\b/.test(navigator.userAgent);
const desktopTargets = new Map();
let nextTargetNumber = 1;
if (supportsMultipleTargets) {
  $("#desktop-target-help").hidden = false;
  $(".status-bar").hidden = true;
}
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
let draggingSketchGun = null;
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
  sketcher?.positionMarkers();
  updateLocationPositions();
  updateRangeChipPosition();
  updateAimOverlay();
}

function gameCompassAim(bearingDegrees) {
  const normalized = ((bearingDegrees % 360) + 360) % 360;
  const bearing = Math.round(normalized * 1e9) / 1e9;
  const markIndex = Math.floor(bearing / 15 + 0.5) % 24;
  const markDegrees = markIndex * 15;
  const directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  const direction = directions[Math.floor(markIndex / 3)];
  const ticks = markIndex % 3;
  return {
    bearing,
    markDegrees,
    instruction:ticks ? `${direction} +${ticks}` : direction,
  };
}

function updateAimCompass(bearingDegrees) {
  const aim = Number.isFinite(bearingDegrees) ? gameCompassAim(bearingDegrees) : null;
  $("#aim").textContent = aim ? aim.instruction : "—";
  $("#aim-degrees").textContent = aim ? `${aim.markDegrees}° tick` : "—";
  $("#aim-mark").style.setProperty("--angle", `${aim?.markDegrees || 0}deg`);
  $("#aim-needle").style.setProperty("--angle", `${aim?.bearing || 0}deg`);
}

function missionBearing(point = target) {
  if (!gun || !point) return null;
  const dx = point.x - gun.x;
  const dy = point.y - gun.y;
  if (dx === 0 && dy === 0) return null;
  return (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
}

function compassGuideDirections(bearingDegrees) {
  const first = Math.floor(bearingDegrees / 45) * 45;
  return [first, (first + 45) % 360];
}

function compassMinorTickDirections(bearingDegrees) {
  const first = Math.floor(bearingDegrees / 45) * 45;
  return [(first + 15) % 360, (first + 30) % 360];
}

function rayPoint(origin, bearingDegrees, distance) {
  const radians = bearingDegrees * Math.PI / 180;
  const dx = Math.sin(radians);
  const dy = -Math.cos(radians);
  return {x:origin.x + dx * distance, y:origin.y + dy * distance, dx, dy};
}

function updateAimOverlay() {
  const point = supportsMultipleTargets
    ? (desktopTargets.size === 1 ? desktopTargets.values().next().value.point : null)
    : target;
  const bearing = missionBearing(point);
  if (bearing == null) {
    aimOverlay.replaceChildren();
    return;
  }
  const origin = screenPoint(gun);
  const targetPoint = screenPoint(point);
  const shotLength = Math.hypot(targetPoint.x - origin.x, targetPoint.y - origin.y);
  const labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  const namedDirections = compassGuideDirections(bearing);
  const directions = [
    {direction:namedDirections[0], label:labels[Math.round(namedDirections[0] / 45) % 8]},
    ...compassMinorTickDirections(bearing).map((direction, index) => ({
      direction, label:`+${index + 1}`,
    })),
    {direction:namedDirections[1], label:labels[Math.round(namedDirections[1] / 45) % 8]},
  ];
  const guides = directions.map(({direction, label}) => {
    const end = rayPoint(origin, direction, shotLength);
    const labelX = end.x - end.dx * 9;
    const labelY = end.y - end.dy * 9;
    const width = label.length === 1 ? 22 : 30;
    return `<line class="aim-guide" data-bearing="${direction}" x1="${origin.x}" y1="${origin.y}" x2="${end.x}" y2="${end.y}"/><g transform="translate(${labelX} ${labelY})"><rect class="aim-guide-label-bg" x="${-width / 2}" y="-9" width="${width}" height="18" rx="5"/><text class="aim-guide-label">${label}</text></g>`;
  }).join("");
  aimOverlay.innerHTML = guides;
}

function resetView() {
  if (!mapImage.naturalWidth) return;
  const rect = mapWrap.getBoundingClientRect();
  baseScale = Math.min(rect.width / mapImage.naturalWidth, rect.height / mapImage.naturalHeight);
  sceneWidth = mapImage.naturalWidth * baseScale;
  sceneHeight = mapImage.naturalHeight * baseScale;
  scene.style.width = `${sceneWidth}px`;
  scene.style.height = `${sceneHeight}px`;
  zoom = applicationMode === "calculator" ? Math.min(MAX_ZOOM, Math.max(rect.width / sceneWidth, rect.height / sceneHeight)) : 1;
  translateX = (rect.width - sceneWidth * zoom) / 2;
  translateY = (rect.height - sceneHeight * zoom) / 2;
  renderLocations();
  renderImpacts();
  updateMissionGeometry();
  applyView();
}

function fitWholeMap() {
  resetView();
  if (zoom === 1) return;
  const rect = mapWrap.getBoundingClientRect();
  zoom = 1;
  translateX = (rect.width - sceneWidth) / 2;
  translateY = (rect.height - sceneHeight) / 2;
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
  if (sketcher?.active) { gunAnchor.hidden = true; targetAnchor.hidden = true; return; }
  if (gun) setAnchor(gunAnchor, gun);
  if (target) setAnchor(targetAnchor, target);
  else targetAnchor.hidden = true;
  for (const [anchor, entry] of desktopTargets) setAnchor(anchor, entry.point);
  if (supportsMultipleTargets) positionDesktopReadouts();
}

function updateLocationPositions() {
  // Names stay attached to their map reference. Do not reflow them for zoom,
  // nearby guns or viewport edges; the map container clips them naturally.
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
  let bottom = 64;
  if (applicationMode === "calculator") {
    const readout = $(".status-bar").getBoundingClientRect();
    if (readout.height > 0) bottom = Math.max(bottom, rect.bottom - readout.top + 8);
  }
  // Prefer the side beyond the target, away from the gun-to-target segment.
  const xs = [second.x+24, second.x-width-24];
  const ys = [second.y+24, second.y-height-24];
  if (second.x < first.x) xs.reverse();
  if (second.y < first.y) ys.reverse();
  const candidates = xs.flatMap(x => ys.map(y => ({
    x:Math.max(8, Math.min(rect.width-width-8, x)),
    y:Math.max(8, Math.min(rect.height-height-bottom, y)),
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
  updateMarkerPositions();
  if (supportsMultipleTargets) {
    for (const entry of desktopTargets.values()) positionShotLine(entry.line, entry.point);
    updateAimOverlay();
    return;
  }
  if (!gun || !target) {
    shotLine.hidden = true;
    rangeChip.hidden = true;
    updateAimOverlay();
    return;
  }
  positionShotLine(shotLine, target);
  rangeChip.hidden = !latestSolution;
  updateRangeChipPosition();
  updateAimOverlay();
}

function positionShotLine(line, point) {
  line.hidden = !gun;
  if (!gun) return;
  const gx = gun.x * baseScale;
  const gy = gun.y * baseScale;
  const tx = point.x * baseScale;
  const ty = point.y * baseScale;
  const dx = tx - gx;
  const dy = ty - gy;
  line.style.left = `${gx}px`;
  line.style.top = `${gy}px`;
  line.style.width = `${Math.hypot(dx, dy)}px`;
  line.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
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
  if (supportsMultipleTargets) {
    for (const entry of desktopTargets.values()) clearDesktopSolution(entry);
    updateMissionGeometry();
    return;
  }
  for (const id of ["elevation", "fuze"]) {
    $(`#${id}`).textContent = "—";
  }
  rangeChip.hidden = true;
  $("#distance").textContent = "—";
  $("#height").textContent = "—";
  $("#explosion-height").textContent = "—";
  updateAimCompass(null);
  shotLine.classList.remove("clear", "obstructed");
  updateMissionGeometry();
}

function clearMission(resetMap = true) {
  gun = null;
  target = null;
  for (const [anchor, entry] of desktopTargets) {
    entry.request = null;
    anchor.remove(); entry.line.remove(); entry.readout.remove();
  }
  desktopTargets.clear();
  nextTargetNumber = 1;
  refreshCalibrationTargets();
  gunAnchor.hidden = true;
  targetAnchor.hidden = true;
  shotLine.hidden = true;
  rangeChip.hidden = true;
  clearSolution();
  if (resetMap) resetView();
  setMode("pan");
}

function setMode(nextMode) {
  if (sketcher?.active) { mode = "pan"; sketcher.status(); return; }
  mode = nextMode;
  const placingTarget = mode === "target";
  $("#gun-mode").classList.toggle("active", mode === "gun");
  $("#target-mode").classList.toggle("active", placingTarget);
  for (const [id, kind] of [["mobile-gun-mode", "gun"], ["mobile-target-mode", "target"]]) {
    const placing = kind === "target" ? placingTarget : mode === kind;
    $("#" + id).classList.toggle("active", placing);
    $("#" + id).setAttribute("aria-pressed", String(placing));
  }
  modePill.classList.toggle("idle-hint", !(supportsMultipleTargets && placingTarget));
  $("#impact-mode").classList.toggle("active", mode === "impact");
  modePill.textContent = mode === "pan"
    ? "HOLD & DRAG TO PAN"
    : mode === "gun" ? "CLICK MAP TO PLACE GUN" : mode === "impact"
      ? "CLICK WHERE THE SHOT LANDED" : supportsMultipleTargets && placingTarget
        ? "CLICK MAP TO ADD A TARGET" : "CLICK MAP TO PLACE TARGET";
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
  refreshCalibrationTargets();
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
    showStatus("SWITCH TO CALIBRATION TEST TO RECORD IMPACTS");
    return;
  }
  if (supportsMultipleTargets && desktopTargets.size > 1 && !desktopCalibrationTarget()) {
    showStatus("CHOOSE A TARGET IN THE CALIBRATION CONTROLS");
    return;
  }
  const calibrationSolution = () => supportsMultipleTargets ? desktopCalibrationTarget()?.solution : latestSolution;
  if (!mapReady || !calibrationSolution()?.calculation_id) {
    showStatus("CALCULATE A SHOT BEFORE MARKING IMPACT");
    return;
  }
  const actualElevation = Number($("#actual-elevation").value);
  if (!Number.isFinite(actualElevation) || $("#actual-elevation").value.trim() === "") {
    showStatus("ENTER THE ACTUAL ELEVATION FIRED");
    $("#actual-elevation").focus();
    return;
  }
  const shotId = calibrationSolution().calculation_id;
  const point = exactPoint || imagePoint(clientX, clientY);
  showStatus("SAVING IMPACT...");
  try {
    await nativeApi.recordImpact({calculation_id:shotId, impact:point,
                                  actual_elevation_degrees:actualElevation});
    if (calibrationSolution()?.calculation_id !== shotId) return;
    impacts.push(point);
    renderImpacts();
    showStatus(`IMPACT ${impacts.length} SAVED`);
  } catch (error) {
    if (calibrationSolution()?.calculation_id === shotId) showStatus(error.message);
  }
}

function createDesktopTarget(point) {
  const number = nextTargetNumber++;
  const name = `TARGET ${number}`;
  const anchor = document.createElement("div");
  anchor.className = "marker-anchor desktop-target";
  anchor.dataset.marker = "target";
  anchor.title = "Drag to move · Right-click to remove";
  anchor.append(globalThis.WorCalcMapMarkers.create("target", name));

  const line = document.createElement("div");
  line.className = "shot-line";
  scene.append(line);

  const readout = document.createElement("div");
  readout.className = "range-chip target-readout";
  readout.dataset.targetNumber = String(number);
  const heading = document.createElement("small");
  heading.className = "target-readout-heading";
  const metrics = ["ELEVATION", "FUZE", "BURST HEIGHT"].map(label => {
    const column = document.createElement("div");
    const title = document.createElement("small");
    const value = document.createElement("b");
    title.textContent = label;
    column.append(title, value);
    return {column, title, value};
  });
  readout.append(heading, ...metrics.map(metric => metric.column));
  mapWrap.append(readout);
  mapWrap.append(anchor);
  const entry = {number, name, point, line, readout, heading, metrics, solution:null, request:null, error:false};
  desktopTargets.set(anchor, entry);
  renderDesktopSolution(entry);
  refreshCalibrationTargets();
}

function positionDesktopReadouts() {
  const viewport = mapWrap.getBoundingClientRect();
  const occupied = [];
  for (const {readout, point} of desktopTargets.values()) {
    readout.hidden = !gun;
    if (!gun) continue;
    const size = {width:readout.offsetWidth || 200, height:readout.offsetHeight || 62};
    const box = globalThis.WorCalcFireReadouts.position(screenPoint(point), viewport, size, occupied, true);
    readout.style.left = `${box.x}px`;
    readout.style.top = `${box.y}px`;
    occupied.push(box);
  }
}

function renderDesktopSolution(entry) {
  const {solution, heading, metrics, line} = entry;
  const aim = solution && Number.isFinite(solution.bearing_degrees) ? gameCompassAim(solution.bearing_degrees).instruction : null;
  const status = entry.request ? "CALCULATING…" : entry.error ? "CALCULATION FAILED" : aim;
  heading.textContent = status ? `${entry.name} · ${status}` : entry.name;
  metrics[0].title.textContent = elevationLabel(solution);
  metrics[0].value.textContent = solution ? globalThis.WorCalcFireReadouts.elevationText(solution.elevation_degrees) : "—";
  metrics[1].value.textContent = globalThis.WorCalcFireReadouts.fuzeText(solution?.fuze_seconds);
  metrics[2].value.textContent = solution ? explosionHeightText(solution.height_above_target_metres) : "—";
  showClearance(line, solution);
}

function clearDesktopSolution(entry) {
  entry.request = null;
  entry.solution = null;
  entry.error = false;
  renderDesktopSolution(entry);
}

function desktopCalibrationTarget() {
  if (desktopTargets.size === 1) return desktopTargets.values().next().value;
  const number = Number($("#calibration-target").value);
  return [...desktopTargets.values()].find(entry => entry.number === number);
}

function refreshCalibrationTargets() {
  if (!supportsMultipleTargets) return;
  const select = $("#calibration-target");
  const previous = select.value;
  addOptions(select, ["", ...[...desktopTargets.values()].map(entry => String(entry.number))]);
  select.children[0].textContent = "Choose target";
  for (const option of Array.from(select.children).slice(1)) option.textContent = `Target ${option.value}`;
  select.value = [...desktopTargets.values()].some(entry => String(entry.number) === previous) ? previous : "";
  $("#calibration-target-field").hidden = !calibrationMode() || desktopTargets.size < 2;
  if (calibrationMode()) setActualElevation(desktopCalibrationTarget()?.solution);
}

function moveMarker(name, clientX, clientY, anchor = null) {
  const point = imagePoint(clientX, clientY);
  if (supportsMultipleTargets && name !== "gun") {
    if (anchor) {
      const entry = desktopTargets.get(anchor);
      entry.point = point;
      clearDesktopSolution(entry);
    } else createDesktopTarget(point);
  } else {
    clearSolution();
    if (name === "gun") gun = point;
    else target = point;
  }
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
    const objectUrl = URL.createObjectURL(await nativeApi.mapImage(map.thumbnail_path, signal));
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
  const namedLocations = [];
  locationAnchors = locations.map((location) => {
    const anchor = document.createElement("span");
    anchor.className = "location-anchor";
    const batteryName = globalThis.WorCalcArtilleryPositions.label(location);
    anchor.hidden = location.kind === "battery" ? !batteryName || !showArtilleryNames : applicationMode === "sketcher";
    const dot = document.createElement("i");
    dot.className = `location-dot ${locationClass(location)}`;
    dot.textContent = location.kind === "gun_spawn" ? "G" : location.kind === "battery" ? "B" : location.kind === "objective" ? "P" : "S";
    const label = location.kind === "gun_spawn" ? "Gun starting position (before movement)"
      : location.kind === "battery" ? "Artillery crew spawn reference" : location.kind;
    dot.hidden = location.kind === "battery";
    dot.title = [location.faction, label, batteryName, location.name].filter(Boolean).join(" · ");
    anchor.append(dot);
    const duplicate = namedLocations.some(item => item.name === batteryName && item.faction === location.faction &&
      Math.hypot(item.x - location.pixel_x, item.y - location.pixel_y) < 4);
    if (batteryName && showArtilleryNames && !duplicate) {
      namedLocations.push({name:batteryName, faction:location.faction, x:location.pixel_x, y:location.pixel_y});
      const name = document.createElement("span");
      name.className = "artillery-position-label";
      name.textContent = batteryName;
      anchor.append(name);
    }
    return anchor;
  });
  layer.replaceChildren(...locationAnchors);
  updateLocationPositions();
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
  if (sketcher?.busy) return;
  cancelThumbnailPrefetch();
  mapReady = false;
  pointers.clear();
  primaryPointerId = null;
  pendingPlacement = null;
  draggingMarker = null;
  draggingSketchGun = null;
  pinching = false;
  currentMap = map;
  $("#map-name").textContent = map.name;
  $("#map-subtitle").textContent = `${map.battlefield.toUpperCase()} / ${map.mode.toUpperCase()} / AREA ${String(map.gameplay_area + 1).padStart(2, "0")}`;
  locations = [];
  locationsReady = false;
  renderLocations();
  clearMission(false);
  if (sketcher?.active) sketcher.mapChanged();
  loadMapImage(map);
  renderMapList($("#map-search").value);
  try {
    const result = await nativeApi.locations(map.identifier);
    if (currentMap?.identifier === map.identifier) {
      locations = result;
      locationsReady = true;
      renderLocations();
      await sketcher?.locationsChanged();
    }
  } catch (error) {
    showStatus(error.message.toUpperCase());
  }
}

async function loadMapImage(map) {
  mapReady = false;
  const requestId = ++mapImageRequestSequence;
  mapImageFetchController?.abort();
  const controller = new AbortController();
  mapImageFetchController = controller;
  mapWrap.classList.add("map-loading");
  modePill.classList.remove("idle-hint");
  showStatus("LOADING SELECTED MAP...");
  try {
    const objectUrl = URL.createObjectURL(await nativeApi.mapImage(map.image_path, controller.signal));
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
      showStatus("SELECTED MAP FAILED TO LOAD");
    });
    preloader.src = objectUrl;
  } catch (error) {
    if (error.name === "AbortError") return;
    if (requestId !== mapImageRequestSequence || currentMap?.identifier !== map.identifier) return;
    mapWrap.classList.remove("map-loading");
    mapImageFetchController = null;
    showStatus("SELECTED MAP FAILED TO LOAD");
  }
}

const calculatorCannons = [
  {value:"3-inch Ordnance", label:"Rifled"},
  {value:"12-pounder Napoleon", label:"Smoothbore"},
];

function populateCannons() {
  if (applicationMode !== "calculator") {
    addOptions($("#cannon-select"), Object.keys(options.weapons));
    $("#cannon-select").value = options.defaults.cannon;
    return;
  }
  $("#cannon-select").replaceChildren(...calculatorCannons.filter(cannon => options.weapons[cannon.value]).map(cannon => {
    const option = document.createElement("option"); option.value = cannon.value; option.textContent = cannon.label; return option;
  }));
  $("#cannon-select").value = options.defaults.cannon === "12-pounder Napoleon" ? "12-pounder Napoleon" : "3-inch Ordnance";
}

function syncQuickSettings() {
  if (!options || applicationMode !== "calculator") return;
  const cannon = calculatorCannons.find(item => item.value === $("#cannon-select").value);
  $("#quick-cannon").textContent = (cannon?.label || "Rifled").toUpperCase();
  $("#quick-projectile").textContent = $("#projectile-select").value.toUpperCase();
  $("#quick-burst").textContent = airburstMode() ? "AIRBURST" : "GROUND";
  for (const [id, name] of [["quick-cannon", "Cannon"], ["quick-projectile", "Ammunition"], ["quick-burst", "Aim point"]]) {
    const button = $("#" + id); button.disabled = false;
    button.setAttribute("aria-label", `${name}: ${button.textContent}. Tap to switch.`);
  }
  $("#quick-cannon").disabled = calculatorCannons.filter(item => options.weapons[item.value]).length < 2;
  $("#quick-projectile").disabled = (options.weapons[$("#cannon-select").value] || []).length < 2;
}

function changeBurstMode() {
  syncQuickSettings();
  clearSolution();
  requestSolution();
}

function updatePhysics() {
  const cannon = $("#cannon-select").value;
  const projectile = $("#projectile-select").value;
  const profile = options.physics[cannon][projectile];
  $("#muzzle-velocity").value = `${profile.speed} m/s`;
  $("#drag-factor").value = `${profile.drag} s⁻¹`;
  syncQuickSettings();
  clearSolution();
  requestSolution();
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
    [maps, options] = await Promise.all([nativeApi.maps(), nativeApi.options()]);
    populateCannons();
    addOptions($("#method-select"), options.methods);
    refreshProjectiles(options.defaults.projectile);
    $("#method-select").value = options.defaults.method;
    $("#calculation-mode").value = "operational";
    $("#burst-mode").value = "ground";
    syncQuickSettings();
    updateCalculationMode();
    if (applicationMode === "sketcher") {
      sketcher = new globalThis.WorCalcSketcher({
      storage:globalThis.worcalcNative.sketchStorage, calculate:nativeApi.calculate,
      map:() => currentMap, locations:() => locations, locationsReady:() => locationsReady,
      mapReady:() => mapReady, options:() => options, position:screenPoint,
      viewport:() => mapWrap.getBoundingClientRect(),
      inspect:() => openPanel($("#sketch-panel")),
      fit:resetView, status:message => {modePill.textContent = message;},
      mission:(savedGun, savedTarget, savedSolution) => {
        clearMission(false); gun = savedGun; target = savedTarget;
        if (savedSolution) displaySolution(savedSolution);
        updateMissionGeometry();
      },
      });
      await sketcher.initialize(maps, options);
    }
    document.body.classList.toggle("sketch-workspace", applicationMode === "sketcher");
    $("#calculator-toolbar").hidden = applicationMode === "sketcher";
    $("#sheet").hidden = applicationMode === "sketcher";
    if (sketcher) {
      $("#sketch-toolbar").hidden = false;
      $("#sketch-panel").hidden = false;
      $("#sketch-panel").inert = false;
      $("#sketch-layer").hidden = false;
      $("#sketch-readouts").hidden = false;
      $("#workspace-title").textContent = "SKETCHER · SAVED FIRE PLANS";
    }
    renderMapList();
    if (maps.length) await selectMap(maps[0]);
    else $("#map-name").textContent = "No maps found";
    $("#workspace").inert = false; drawer.inert = false; sheet.inert = false;
    if (sketcher) await sketcher.enter();
    resetView();
  } catch (error) {
    $("#map-name").textContent = error.message;
    showStatus(error.message);
  }
}

function openPanel(panel) {
  drawer.classList.toggle("open", panel === drawer);
  sheet.classList.toggle("open", panel === sheet);
  $("#sketch-panel")?.classList.toggle("open", panel === $("#sketch-panel"));
  backdrop.classList.toggle("show", panel !== $("#sketch-panel"));
}

function closePanels() {
  drawer.classList.remove("open");
  sheet.classList.remove("open");
  $("#sketch-panel")?.classList.remove("open");
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
  draggingSketchGun = null;
  sketcher?.cancelGunMove();
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
  draggingSketchGun = null;
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
    if (sketcher?.active) return;
    const targetMarker = event.target?.closest?.('[data-marker="target"]');
    markImpact(event.clientX, event.clientY, targetMarker ? desktopTargets.get(targetMarker)?.point || target : null);
    return;
  }
  if (event.button != null && event.button !== 0) return;
  if (!mapReady) return;
  const sketchGunMarker = sketcher?.active ? event.target.closest("[data-sketch-gun],[data-sketch-target]") : null;
  if (sketchGunMarker) {
    if (!pointers.size && !sketcher.beginGunMove(sketchGunMarker.dataset.sketchGun || sketchGunMarker.dataset.sketchTarget, sketchGunMarker.dataset.sketchGun ? "gun" : "target")) return;
  } else if (event.target.closest("button,.map-name,.mode-pill,.status-bar,.range-chip")) return;
  mapWrap.setPointerCapture(event.pointerId);
  pointers.set(event.pointerId, {x:event.clientX, y:event.clientY});
  if (pointers.size === 2) { beginPinch(); return; }
  if (pointers.size > 2) return;
  primaryPointerId = event.pointerId;
  pointerStart = {x:event.clientX, y:event.clientY};
  startTranslation = {x:translateX, y:translateY};
  dragged = false;
  const marker = event.target.closest("[data-marker]");
  draggingMarker = marker;
  draggingSketchGun = sketchGunMarker ? {id:sketchGunMarker.dataset.sketchGun || sketchGunMarker.dataset.sketchTarget, kind:sketchGunMarker.dataset.sketchGun ? "gun" : "target"} : null;
  markerMoveStarted = false;
  pendingPlacement = draggingSketchGun ? null : sketcher?.active ? "sketch" : marker || mode === "pan" ? null : mode;
});

mapWrap.addEventListener("pointermove", (event) => {
  if (!pointers.has(event.pointerId)) return;
  pointers.set(event.pointerId, {x:event.clientX, y:event.clientY});
  if (pointers.size >= 2) { if (!pinching) beginPinch(); updatePinch(); return; }
  if (event.pointerId !== primaryPointerId || !pointerStart) return;
  const dx = event.clientX - pointerStart.x;
  const dy = event.clientY - pointerStart.y;
  if (Math.hypot(dx, dy) > 4) dragged = true;
  if (draggingSketchGun && dragged) {
    sketcher.previewGunMove(imagePoint(event.clientX, event.clientY));
  } else if (draggingMarker && dragged) {
    markerMoveStarted = true;
    moveMarker(draggingMarker.dataset.marker, event.clientX, event.clientY, draggingMarker);
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
    const cancelled = event.type === "pointercancel";
    let shouldRequestSolution = draggingMarker && markerMoveStarted;
    if (draggingSketchGun) {
      const point = draggingSketchGun;
      if (dragged && !cancelled) sketcher.commitGunMove();
      else {sketcher.cancelGunMove(); if (!cancelled) {if (point.kind === "gun") sketcher.selectGun(point.id); else sketcher.selectTarget(point.id, sketcher.tool !== "target");}}
    }
    if (pendingPlacement && !dragged && !cancelled) {
      if (pendingPlacement === "sketch") {
        sketcher.canvasClick(imagePoint(event.clientX, event.clientY));
      } else if (pendingPlacement === "impact") {
        markImpact(event.clientX, event.clientY);
      } else {
        moveMarker(pendingPlacement, event.clientX, event.clientY);
        shouldRequestSolution = true;
      }
      setMode("pan");
    }
    primaryPointerId = null;
    pointerStart = null;
    startTranslation = null;
    draggingMarker = null;
    draggingSketchGun = null;
    markerMoveStarted = false;
    pendingPlacement = null;
    dragged = false;
    if (shouldRequestSolution && (!cancelled || supportsMultipleTargets)) requestSolution();
  }
}

mapWrap.addEventListener("pointerup", endPointer);
mapWrap.addEventListener("contextmenu", event => {
  if (!supportsMultipleTargets || !mapReady || pointers.size || event.button !== 2) return;
  const anchor = event.target.closest('[data-marker="target"]');
  const entry = desktopTargets.get(anchor);
  if (!entry) return;
  event.preventDefault();
  entry.request = null;
  anchor.remove(); entry.line.remove(); entry.readout.remove();
  desktopTargets.delete(anchor);
  refreshCalibrationTargets();
  updateMissionGeometry();
});
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
  if (globalThis.worcalcKillTrackerVisible) return;
  if ($("#workspace").inert) return;
  if (event.target?.closest("input,select,textarea,[contenteditable]:not([contenteditable='false'])") || event.ctrlKey || event.metaKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (sketcher?.active) {
    if (key === "delete" && !event.repeat) {event.preventDefault(); sketcher.deleteSelected();}
    if (key === "g") sketcher.setTool("gun");
    if (key === "t") sketcher.setTool("target");
    if (key === "escape") {sketcher.cancelTool(); closePanels();}
    if (key === "f") resetView();
    return;
  }
  if (key === "g") setMode("gun");
  if (key === "t" && !event.repeat) setMode("target");
  if (key === "i" && calibrationMode()) setMode("impact");
  if (key === "escape") { setMode("pan"); closePanels(); }
  if (key === "f") fitWholeMap();
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
$("#fit-map").addEventListener("click", fitWholeMap);
$("#mobile-fit").addEventListener("click", fitWholeMap);
$("#mobile-gun-mode").addEventListener("click", () => setMode(mode === "gun" ? "pan" : "gun"));
$("#mobile-target-mode").addEventListener("click", () => setMode(mode === "target" ? "pan" : "target"));
$("#mobile-advanced").addEventListener("click", () => openPanel(sheet));
$("#quick-cannon").addEventListener("click", () => {
  if (!options || applicationMode !== "calculator") return;
  const next = calculatorCannons.find(item => options.weapons[item.value] && item.value !== $("#cannon-select").value);
  if (!next) return;
  const projectile = $("#projectile-select").value;
  $("#cannon-select").value = next.value; refreshProjectiles(projectile);
});
$("#quick-projectile").addEventListener("click", () => {
  if (!options || applicationMode !== "calculator") return;
  const values = options.weapons[$("#cannon-select").value] || [];
  if (values.length < 2) return;
  $("#projectile-select").value = values[(values.indexOf($("#projectile-select").value) + 1) % values.length];
  updatePhysics();
});
$("#quick-burst").addEventListener("click", () => {
  if (!options || applicationMode !== "calculator") return;
  $("#burst-mode").value = airburstMode() ? "ground" : "airburst";
  changeBurstMode();
});
// Pointer activation should not leave a keyboard-focus ring on the last button.
window.addEventListener("click", event => {
  if (applicationMode === "calculator" && event.detail > 0) event.target?.closest?.("button")?.blur();
});
$("#open-drawer").addEventListener("click", () => openPanel(drawer));
$("#open-sheet").addEventListener("click", () => openPanel(sketcher?.active ? $("#sketch-panel") : sheet));
backdrop.addEventListener("click", closePanels);
document.querySelectorAll(".close").forEach((button) => button.addEventListener("click", closePanels));
$("#map-search").addEventListener("input", (event) => {
  cancelThumbnailPrefetch();
  renderMapList(event.target.value);
});
$("#artillery-names").addEventListener("change", (event) => {
  showArtilleryNames = event.target.checked;
  renderLocations();
});
$("#cannon-select").addEventListener("change", () => refreshProjectiles($("#projectile-select").value));
$("#projectile-select").addEventListener("change", updatePhysics);
$("#method-select").addEventListener("change", () => {
  clearSolution();
  requestSolution();
});
$("#calculation-mode").addEventListener("change", () => {
  updateCalculationMode();
  clearSolution();
  requestSolution();
});
$("#burst-mode").addEventListener("change", changeBurstMode);
$("#calibration-target").addEventListener("change", () => {
  setActualElevation(desktopCalibrationTarget()?.solution);
});

function solutionInput(point) {
  return {
    map_id:currentMap.identifier,
    gun:{...gun},
    target:{...point},
    cannon:$("#cannon-select").value,
    projectile:$("#projectile-select").value,
    method:$("#method-select").value,
    calibration_mode:calibrationMode(),
    airburst_mode:airburstMode(),
  };
}

async function requestDesktopSolution(entry) {
  const request = solutionInput(entry.point);
  entry.request = request;
  entry.error = false;
  renderDesktopSolution(entry);
  try {
    const data = await nativeApi.calculate(request);
    if (entry.request !== request) return;
    entry.solution = data;
    if (calibrationMode() && desktopCalibrationTarget() === entry) setActualElevation(data);
  } catch {
    if (entry.request === request) entry.error = true;
  } finally {
    if (entry.request === request) {
      entry.request = null;
      renderDesktopSolution(entry);
      positionDesktopReadouts();
    }
  }
}

async function requestSolution() {
  if (sketcher?.active) return;
  if (!gun || !currentMap || !mapReady) return;
  if (supportsMultipleTargets) {
    for (const entry of desktopTargets.values()) {
      if (!entry.request && !entry.solution) requestDesktopSolution(entry);
    }
    return;
  }
  if (!target) return;
  clearSolution();
  const requestId = ++solutionRequestSequence;
  let succeeded = false;
  mapWrap.classList.add("solution-loading");
  modePill.classList.remove("idle-hint");
  showStatus("CALCULATING FIRE SOLUTION...");
  updateMissionGeometry();
  try {
    const data = await nativeApi.calculate(solutionInput(target));
    if (requestId !== solutionRequestSequence) return;
    displaySolution(data);
    succeeded = true;
    updateMissionGeometry();
  } catch (error) {
    if (requestId === solutionRequestSequence) showStatus(error.message.toUpperCase());
  } finally {
    if (requestId === solutionRequestSequence) {
      mapWrap.classList.remove("solution-loading");
      if (succeeded) setMode(mode);
      if (succeeded && latestSolution?.elevation_degrees == null) {
        showStatus("NO SOLUTION FOR THIS RANGE AND HEIGHT");
      }
      updateMissionGeometry();
    }
  }
}

function setActualElevation(data) {
  $("#actual-elevation").value = data?.elevation_degrees == null
    ? "" : (Math.round(data.elevation_degrees * 100) / 100).toFixed(2);
}

function elevationLabel(data) {
  return data?.elevation_source?.startsWith("saved_") ? "SAVED ELEVATION" :
    data?.elevation_source === "calibration_test" ? "TEST ELEVATION" :
    data?.elevation_source === "terrain_clearance" ? "CLEARANCE" : "ELEVATION";
}

function explosionHeightText(height) {
  return height == null ? "N/A" : `${height >= 0 ? "+" : ""}${height.toFixed(1)} m`;
}

function showClearance(line, data) {
  line.classList.toggle("clear", data?.clearance_status === "clear");
  line.classList.toggle("obstructed", data?.clearance_status === "obstructed");
}

function displaySolution(data) {
  latestSolution = data;
  setActualElevation(data);
  $("#distance").textContent = `${data.slant_range_yards.toFixed(0)} yd`;
  updateAimCompass(data.bearing_degrees);
  $("#height").textContent = data.height_difference_metres == null ? "N/A" : `${data.height_difference_metres.toFixed(1)} m`;
  $("#elevation").textContent = globalThis.WorCalcFireReadouts.elevationText(data.elevation_degrees);
  $("#elevation-label").textContent = elevationLabel(data);
  $("#fuze").textContent = globalThis.WorCalcFireReadouts.fuzeText(data.fuze_seconds);
  $("#explosion-height").textContent = explosionHeightText(data.height_above_target_metres);
  showClearance(shotLine, data);
}

window.addEventListener("resize", resetView);
window.addEventListener("beforeunload", () => {
  thumbnailPrefetchController?.abort();
  mapImageFetchController?.abort();
  for (const objectUrl of thumbnailObjectUrls.values()) URL.revokeObjectURL(objectUrl);
  if (currentMapObjectUrl) URL.revokeObjectURL(currentMapObjectUrl);
});
load();
