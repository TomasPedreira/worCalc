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
let locations = [];
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
let expandedBattlefield = null;
const expandedModes = new Map();
let solutionRequestSequence = 0;

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
  translateX = scaledWidth <= rect.width
    ? (rect.width - scaledWidth) / 2
    : Math.min(0, Math.max(rect.width - scaledWidth, translateX));
  translateY = scaledHeight <= rect.height
    ? (rect.height - scaledHeight) / 2
    : Math.min(0, Math.max(rect.height - scaledHeight, translateY));
}

function applyView() {
  clampTranslation();
  scene.style.setProperty("--inverse-zoom", String(1 / zoom));
  scene.style.transform = `translate(${translateX}px,${translateY}px) scale(${zoom})`;
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
  anchor.style.left = `${point.x * baseScale}px`;
  anchor.style.top = `${point.y * baseScale}px`;
  anchor.hidden = false;
}

function updateRangeChipPosition() {
  if (!gun || !target) return;
  const first = screenPoint(gun);
  const second = screenPoint(target);
  rangeChip.style.left = `${(first.x + second.x) / 2}px`;
  rangeChip.style.top = `${(first.y + second.y) / 2}px`;
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
}

function clearSolution() {
  cancelPendingSolution();
  latestSolution = null;
  for (const id of ["elevation", "fuze"]) {
    $(`#${id}`).textContent = "—";
  }
  rangeChip.hidden = true;
  $("#distance").textContent = "—";
  $("#bearing").textContent = "—";
  $("#height").textContent = "—";
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
  modePill.textContent = mode === "pan"
    ? "HOLD & DRAG TO PAN"
    : mode === "gun" ? "TAP MAP TO PLACE GUN" : "TAP MAP TO PLACE TARGET";
}

function moveMarker(name, clientX, clientY) {
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

function createMapCard(map) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `map-card${map.identifier === currentMap?.identifier ? " active" : ""}`;
  const image = document.createElement("img");
  image.src = map.image_url;
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

function renderLocations() {
  const layer = $("#location-layer");
  layer.replaceChildren(...locations.map((location) => {
    const anchor = document.createElement("span");
    anchor.className = "location-anchor";
    anchor.style.left = `${location.pixel_x * baseScale}px`;
    anchor.style.top = `${location.pixel_y * baseScale}px`;
    const dot = document.createElement("i");
    dot.className = `location-dot ${locationClass(location)}`;
    dot.textContent = location.kind === "battery" ? "B" : location.kind === "objective" ? "P" : "S";
    dot.title = [location.faction, location.kind, location.name].filter(Boolean).join(" · ");
    anchor.append(dot);
    return anchor;
  }));
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
      expandedBattlefield = expandedBattlefield === battlefield ? null : battlefield;
      renderMapList($("#map-search").value);
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
        else expandedModes.set(battlefield, gameMode);
        renderMapList($("#map-search").value);
      });
      modeHeading.append(modeToggle);
      const mapCards = document.createElement("div");
      mapCards.className = "map-variants";
      mapCards.hidden = !modeExpanded;
      mapCards.append(...modeMaps.map(createMapCard));
      modeGroup.append(modeHeading, mapCards);
      return modeGroup;
    }));
    group.append(heading, modeGroups);
    return group;
  }));
}

async function selectMap(map) {
  currentMap = map;
  expandedBattlefield = map.battlefield;
  expandedModes.set(map.battlefield, map.mode);
  $("#map-name").textContent = map.name;
  $("#map-subtitle").textContent = `${map.battlefield.toUpperCase()} / ${map.mode.toUpperCase()} / AREA ${String(map.gameplay_area + 1).padStart(2, "0")}`;
  locations = [];
  renderLocations();
  clearMission(false);
  mapImage.src = map.image_url;
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

function updatePhysics() {
  const cannon = $("#cannon-select").value;
  const projectile = $("#projectile-select").value;
  const profile = options.physics[cannon][projectile];
  $("#muzzle-velocity").value = `${profile.speed} m/s`;
  $("#drag-factor").value = `${profile.drag} s⁻¹`;
  clearSolution();
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
  pendingPlacement = marker ? null : (mode === "gun" ? "gun" : mode === "target" ? "target" : null);
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
      cancelPendingSolution();
      moveMarker(pendingPlacement, event.clientX, event.clientY);
      setMode("pan");
      shouldRequestSolution = true;
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
mapWrap.addEventListener("pointercancel", endPointer);
mapImage.addEventListener("load", resetView);
$("#gun-mode").addEventListener("click", () => setMode(mode === "gun" ? "pan" : "gun"));
$("#target-mode").addEventListener("click", () => setMode(mode === "target" ? "pan" : "target"));
$("#open-drawer").addEventListener("click", () => openPanel(drawer));
$("#open-sheet").addEventListener("click", () => openPanel(sheet));
backdrop.addEventListener("click", closePanels);
document.querySelectorAll(".close").forEach((button) => button.addEventListener("click", closePanels));
$("#map-search").addEventListener("input", (event) => renderMapList(event.target.value));
$("#cannon-select").addEventListener("change", () => refreshProjectiles());
$("#projectile-select").addEventListener("change", updatePhysics);
$("#method-select").addEventListener("change", clearSolution);

async function requestSolution() {
  if (!gun || !target || !currentMap) return;
  const requestId = ++solutionRequestSequence;
  const requestedGun = {...gun};
  const requestedTarget = {...target};
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
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Calculation failed");
    if (requestId !== solutionRequestSequence) return;
    latestSolution = data;
    $("#distance").textContent = `${data.slant_range_yards.toFixed(0)} yd`;
    $("#bearing").textContent = `${data.bearing_degrees.toFixed(0).padStart(3,"0")}° ${data.bearing_direction}`;
    $("#height").textContent = data.height_difference_metres == null ? "N/A" : `${data.height_difference_metres.toFixed(1)} m`;
    $("#elevation").textContent = data.elevation_degrees == null ? "N/A" : `${data.elevation_degrees.toFixed(3)}°`;
    $("#fuze").textContent = data.fuze_seconds == null ? "N/A" : `${data.fuze_seconds.toFixed(3)} s`;
    updateMissionGeometry();
  } catch (error) {
    if (requestId === solutionRequestSequence) modePill.textContent = error.message.toUpperCase();
  } finally {
    if (requestId === solutionRequestSequence) {
      updateMissionGeometry();
    }
  }
}

window.addEventListener("resize", resetView);
load();
