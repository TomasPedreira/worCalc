/* Shared plan library: geometry is independent of gun-to-target fire settings. */
(() => {
  const VERSION = 1;
  const MAX_BYTES = 5 * 1024 * 1024;
  const copy = value => JSON.parse(JSON.stringify(value));
  const emptyLibrary = () => ({version:VERSION, maps:{}});
  const fail = message => { throw Error(message); };
  const text = (value, name) => {
    if (typeof value !== "string" || !value.trim() || value.length > 200) fail(`Invalid ${name}`);
  };
  function validateLibrary(value, maps, options) {
    if (JSON.stringify(value).length > MAX_BYTES) fail("Plan file is too large");
    if (!value || value.version !== VERSION || !value.maps || Array.isArray(value.maps) || typeof value.maps !== "object") {
      fail("Unsupported sketch plan format");
    }
    const catalog = new Map(maps.map(map => [map.identifier, map]));
    for (const [id, plan] of Object.entries(value.maps)) {
      const map = catalog.get(id);
      if (!map) fail(`Unknown map in plan: ${id}`);
      if (!plan || plan.map_id !== id || plan.map_name !== map.name || plan.battlefield !== (map.battlefield || "") ||
          plan.mode !== (map.mode || "") || plan.gameplay_area !== (map.gameplay_area ?? 0) ||
          plan.width !== map.width_pixels || plan.height !== map.height_pixels) {
        fail(`Plan does not match this map: ${map.name}`);
      }
      if (![plan.guns, plan.targets, plan.configurations].every(Array.isArray) ||
          plan.guns.length > 500 || plan.targets.length > 2000 || plan.configurations.length > 10000) fail("Invalid plan contents");
      for (const key of ["next_gun_id", "next_target_id"]) if (plan[key] != null && (!Number.isSafeInteger(plan[key]) || plan[key] < 1)) fail("Invalid point ID counter");
      const validatePoints = (points, label) => {
        const ids = new Set();
        for (const point of points) {
          text(point.id, `${label} identifier`);
          if (ids.has(point.id)) fail(`Duplicate ${label} identifier`);
          ids.add(point.id);
          if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0 || point.y < 0 || point.x > plan.width || point.y > plan.height) {
            fail(`${label} is outside the map`);
          }
        }
        return new Map(points.map(point => [point.id, point]));
      };
      const guns = validatePoints(plan.guns, "gun");
      const targets = validatePoints(plan.targets, "target");
      for (const gun of guns.values()) if (!options.weapons[gun.cannon]) fail("Unknown cannon in plan");
      const pairs = new Set();
      for (const setting of plan.configurations) {
        const gun = guns.get(setting.gun_id), target = targets.get(setting.target_id);
        if (!gun || !target) fail("Fire configuration refers to a missing point");
        if (gun.x === target.x && gun.y === target.y) fail("Gun and target must be different points");
        const pair = JSON.stringify([setting.gun_id, setting.target_id]);
        if (pairs.has(pair)) fail("Duplicate fire configuration for gun and target");
        pairs.add(pair);
        if (!options.weapons[gun.cannon].includes(setting.projectile) || typeof setting.airburst_mode !== "boolean") fail("Invalid artillery profile in plan");
        if (!Number.isFinite(setting.elevation_degrees) || setting.elevation_degrees < -8 || setting.elevation_degrees > 14 ||
            !Number.isFinite(setting.fuze_seconds) || setting.fuze_seconds < 0 || setting.fuze_seconds > 120) fail("Invalid elevation or fuze in plan");
        const solution = setting.solution;
        if (!solution || solution.map_id !== id || solution.cannon !== gun.cannon || solution.projectile !== setting.projectile ||
            solution.airburst_mode !== setting.airburst_mode || solution.calibration_mode !== false ||
            !Number.isFinite(solution.bearing_degrees) || !Number.isFinite(solution.slant_range_yards) ||
            !Number.isFinite(solution.elevation_degrees) || !Number.isFinite(solution.fuze_seconds)) fail("Invalid calculated solution in plan");
        for (const [key, number] of Object.entries(solution)) {
          if (typeof number === "number" && !Number.isFinite(number)) fail(`Invalid solution field: ${key}`);
        }
        for (const key of ["height_difference_metres", "height_above_target_metres"]) {
          if (solution[key] != null && !Number.isFinite(solution[key])) fail(`Invalid solution field: ${key}`);
        }
        if (solution.elevation_source != null && typeof solution.elevation_source !== "string") fail("Invalid elevation source");
        if (solution.clearance_status != null && !["clear", "obstructed"].includes(solution.clearance_status)) fail("Invalid clearance status");
        if (typeof setting.notes !== "string" || setting.notes.length > 2000) fail("Invalid target notes");
      }
    }
    const checked = copy(value);
    for (const plan of Object.values(checked.maps)) for (const point of [...plan.guns, ...plan.targets]) delete point.name;
    return checked;
  }
  function createPlan(map, locations, cannon, weapons = {}) {
    const guns = [];
    for (const location of locations.filter(location => location.kind === "gun_spawn")) {
      if (!Number.isFinite(location.pixel_x) || !Number.isFinite(location.pixel_y) || location.pixel_x < 0 || location.pixel_y < 0 ||
          location.pixel_x > map.width_pixels || location.pixel_y > map.height_pixels) continue;
      if (guns.some(gun => Math.hypot(gun.x - location.pixel_x, gun.y - location.pixel_y) < 1)) continue;
      const profile = Object.keys(weapons).sort((a,b) => b.length-a.length).find(weapon => location.name.startsWith(weapon));
      guns.push({id:`gun-${guns.length + 1}`, x:location.pixel_x, y:location.pixel_y, cannon:profile || cannon});
    }
    return {map_id:map.identifier, map_name:map.name, battlefield:map.battlefield || "", mode:map.mode || "",
      gameplay_area:map.gameplay_area ?? 0, width:map.width_pixels, height:map.height_pixels, guns, targets:[], configurations:[]};
  }
  function configuration(plan, gunId, targetId) {
    return plan.configurations.find(setting => setting.gun_id === gunId && setting.target_id === targetId) || null;
  }
  function nextPointId(plan, kind) {
    const points = kind === "gun" ? plan.guns : plan.targets;
    const sequence = points.reduce((max, point) => {
      const suffix = point.id.startsWith(kind + "-") ? Number(point.id.slice(kind.length + 1)) : 0;
      return Number.isSafeInteger(suffix) ? Math.max(max, suffix) : max;
    }, 0);
    // Retain a counter so deleted IDs are not assigned to a different point.
    return `${kind}-${Math.max(sequence + 1, plan["next_" + kind + "_id"] || 1)}`;
  }
  function retainPointId(plan, kind, id) {
    const number = Number(id.slice(kind.length + 1));
    if (id.startsWith(kind + "-") && Number.isSafeInteger(number)) plan["next_" + kind + "_id"] = Math.max(plan["next_" + kind + "_id"] || 1, number + 1);
  }
  function visibleTargets(plan, gunId) {
    return plan.targets.map(target => ({...target, configuration:configuration(plan, gunId, target.id)}));
  }
  function saveConfiguration(plan, gunId, target, setting) {
    if (!plan.guns.some(gun => gun.id === gunId)) fail("Select a gun first");
    let savedTarget = plan.targets.find(point => point.id === target.id);
    if (!savedTarget) savedTarget = plan.targets.find(point => Math.hypot(point.x-target.x, point.y-target.y) < 1);
    if (!savedTarget) { savedTarget = {id:target.id, x:target.x, y:target.y}; plan.targets.push(savedTarget); retainPointId(plan, "target", target.id); }
    else if (savedTarget.id === target.id) moveTarget(plan, target.id, target);
    const next = {...copy(setting), gun_id:gunId, target_id:savedTarget.id};
    const existing = configuration(plan, gunId, savedTarget.id);
    if (existing) Object.assign(existing, next);
    else plan.configurations.push(next);
    return savedTarget.id;
  }
  function removeGun(plan, gunId) {
    retainPointId(plan, "gun", gunId);
    plan.guns = plan.guns.filter(gun => gun.id !== gunId);
    plan.configurations = plan.configurations.filter(setting => setting.gun_id !== gunId);
  }
  function moveGun(plan, gunId, point) {
    const gun = plan.guns.find(gun => gun.id === gunId);
    if (!gun) fail("Select a gun first");
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0 || point.y < 0 || point.x > plan.width || point.y > plan.height) {
      fail("Gun is outside the map");
    }
    if (gun.x === point.x && gun.y === point.y) return;
    gun.x = point.x; gun.y = point.y;
    plan.configurations = plan.configurations.filter(setting => setting.gun_id !== gunId);
  }
  function unlinkTarget(plan, gunId, targetId) {
    plan.configurations = plan.configurations.filter(setting => setting.gun_id !== gunId || setting.target_id !== targetId);
  }
  function moveTarget(plan, targetId, point) {
    const target = plan.targets.find(target => target.id === targetId);
    if (!target) fail("Select a target first");
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0 || point.y < 0 || point.x > plan.width || point.y > plan.height) fail("Target is outside the map");
    if (target.x === point.x && target.y === point.y) return;
    target.x = point.x; target.y = point.y;
    plan.configurations = plan.configurations.filter(setting => setting.target_id !== targetId);
  }
  function removeTarget(plan, targetId) {
    retainPointId(plan, "target", targetId);
    plan.targets = plan.targets.filter(target => target.id !== targetId);
    plan.configurations = plan.configurations.filter(setting => setting.target_id !== targetId);
  }
  class LibraryStore {
    constructor(adapter, maps, options) {
      this.adapter = adapter; this.maps = maps; this.options = options;
      this.data = emptyLibrary(); this.queue = Promise.resolve(); this.ready = false;
    }
    async load() {
      const saved = await this.adapter.load();
      this.data = validateLibrary(saved || emptyLibrary(), this.maps, this.options);
      this.ready = true;
    }
    update(change) {
      const result = this.queue.catch(() => {}).then(async () => {
        if (!this.ready) fail("Saved plans could not be loaded. Import a valid backup to recover.");
        const next = copy(this.data);
        change(next);
        const checked = validateLibrary(next, this.maps, this.options);
        await this.adapter.save(checked);
        this.data = checked;
      });
      this.queue = result;
      return result;
    }
    import(value) {
      const checked = validateLibrary(value, this.maps, this.options);
      const result = this.queue.catch(() => {}).then(async () => {
        // Import replaces only the maps in the file, preserving other local maps.
        const next = validateLibrary({version:VERSION, maps:{...this.data.maps, ...checked.maps}}, this.maps, this.options);
        await this.adapter.save(next);
        this.data = next; this.ready = true;
      });
      this.queue = result;
      return result;
    }
  }
  globalThis.WorCalcSketch = {VERSION, MAX_BYTES, copy, emptyLibrary, validateLibrary, createPlan,
    configuration, visibleTargets, nextPointId, retainPointId, saveConfiguration, moveGun, moveTarget, removeGun, unlinkTarget, removeTarget, LibraryStore};
})();
