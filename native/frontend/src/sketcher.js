/* Saved-plan presentation; native calculation, persistence and navigation are injected. */
(() => {
  const M = globalThis.WorCalcSketch;
  const $ = selector => document.querySelector(selector);
  const label = kind => kind === "gun" ? "Gun" : "Target";
  class Sketcher {
    constructor(hooks) {
      this.hooks = hooks; this.active = false; this.editing = false; this.tool = null;
      this.gunId = null; this.targetId = null; this.selection = null; this.draft = null; this.busy = false;
      this.calculationSequence = 0; this.markers = []; this.readouts = []; this.seeding = new Map(); this.gunMove = null;
      $("#sketch-edit").addEventListener("click", () => this.toggleEdit());
      $("#sketch-view").addEventListener("click", () => {if (this.editing) this.toggleEdit();});
      $("#sketch-add-gun").addEventListener("click", () => this.setTool("gun"));
      $("#sketch-add-target").addEventListener("click", () => this.setTool("target"));
      $("#sketch-fit").addEventListener("click", hooks.fit);
      $("#sketch-gun-select").addEventListener("change", event => this.selectGun(event.target.value || null));
      $("#sketch-form").addEventListener("submit", event => {event.preventDefault(); this.saveDraft();});
      $("#sketch-cancel").addEventListener("click", () => this.cancelDraft());
      $("#sketch-delete").addEventListener("click", () => this.deleteSelected());
      $("#sketch-unlink").addEventListener("click", () => this.unlinkSelected());
      $("#sketch-defaults").addEventListener("click", () => this.useDefaults());
      $("#sketch-calculate").addEventListener("click", () => this.calculateDraft(false));
      for (const id of ["sketch-ammo", "sketch-burst", "sketch-x", "sketch-y"]) {
        $("#" + id).addEventListener("change", () => {if (this.draft?.kind === "target" && this.draft.gun) this.calculateDraft(false);});
      }
      $("#sketch-export").addEventListener("click", () => this.export());
      $("#sketch-import").addEventListener("click", () => {if (this.editing && !this.busy) $("#sketch-file").click();});
      $("#sketch-file").addEventListener("change", event => this.importFile(event.target.files?.[0]));
    }
    async initialize(maps, options) {
      this.store = new M.LibraryStore(this.hooks.storage, maps, options);
      try {await this.store.load();} catch (error) {this.loadError = `Could not load saved plans: ${error.message}`;}
    }
    plan() {
      const map = this.hooks.map();
      return map && (this.store?.data.maps[map.identifier] || M.createPlan(map, this.hooks.locations(), this.hooks.options().defaults.cannon, this.hooks.options().weapons));
    }
    async ensurePlan() {
      const map = this.hooks.map(); if (!map || !this.store?.ready || !this.hooks.locationsReady()) return;
      if (!this.store.data.maps[map.identifier]) {
        if (!this.seeding.has(map.identifier)) {
          const plan = this.plan();
          this.seeding.set(map.identifier, this.store.update(library => {library.maps[map.identifier] ||= M.copy(plan);}));
        }
        try {await this.seeding.get(map.identifier);} finally {this.seeding.delete(map.identifier);}
      }
    }
    async enter() {this.active = true; this.mapChanged(); await this.locationsChanged();}
    leave() {
      this.cancelGunMove(); this.closeEditor(); this.active = false; this.editing = false; this.tool = null;
      this.selection = null; this.markers = []; this.readouts = [];
      $("#sketch-layer").replaceChildren(); $("#sketch-readouts").replaceChildren();
      $("#sketch-connections").replaceChildren();
    }
    mapChanged() {
      this.cancelGunMove(); this.closeEditor(); this.gunId = null; this.targetId = null; this.selection = null; this.tool = null; this.editing = false;
      this.hooks.mission(null, null, null); this.render();
    }
    async locationsChanged() {
      if (!this.active) return;
      try {await this.ensurePlan(); if (this.store?.ready) this.loadError = null;}
      catch (error) {this.loadError = `Could not save starting positions: ${error.message}`;}
      if (this.active) {this.render(); this.status();}
    }
    status() {
      if (!this.active) return;
      this.hooks.status(this.loadError || (this.busy ? "SAVING PLAN..." : this.tool === "gun" ? "CLICK MAP TO PLACE A GUN" :
        this.tool === "target" ? "CLICK MAP TO ADD A TARGET OR USE AN EXISTING POINT" :
        !this.editing ? "VIEW SAVED TARGETS ON THE RIGHT · EDIT TO MAKE CHANGES" :
        this.selection ? "SELECTED DETAILS ON THE RIGHT · SAVE CHANGES · DEL TO DELETE" : "DRAG GUNS OR TARGETS · SELECT TO EDIT"));
    }
    toggleEdit() {
      if (this.busy || !this.store?.ready || this.loadError) return;
      this.cancelGunMove(); this.closeEditor(); this.editing = !this.editing; this.tool = null;
      if (this.targetId && this.plan().targets.some(target => target.id === this.targetId)) this.selectTarget(this.targetId);
      else this.selectGun(this.gunId);
    }
    setTool(tool) {
      if (!this.active || !this.editing || this.busy || !this.store?.ready || this.loadError || (tool === "target" && !this.gunId)) return;
      this.cancelGunMove();
      this.tool = this.tool === tool ? null : tool; this.render(); this.status();
    }
    async canvasClick(point) {
      if (!this.active || !this.editing || !this.hooks.mapReady() || this.busy || !this.tool) return;
      if (this.tool === "gun") {await this.placeGun(point); return;}
      const screen = this.hooks.position(point);
      const existing = this.plan().targets.find(candidate => {
        const position = this.hooks.position(candidate); return Math.hypot(position.x - screen.x, position.y - screen.y) < 22;
      });
      if (existing) this.selectTarget(existing.id);
      else {
        const target = {...point, id:M.nextPointId(this.plan(), "target")};
        this.selection = {kind:"target", id:target.id}; this.targetId = target.id; this.tool = null;
        this.hooks.mission(this.plan().guns.find(gun => gun.id === this.gunId) || null, null, null);
        this.editTarget(target); this.render();
      }
    }
    async placeGun(point) {
      if (!this.active || !this.editing || !this.hooks.mapReady() || !this.store?.ready || this.loadError || this.busy) return;
      const map = this.hooks.map(), plan = this.plan(), selected = plan.guns.find(gun => gun.id === this.gunId);
      const gun = {...point, id:M.nextPointId(plan, "gun"), cannon:selected?.cannon || this.hooks.options().defaults.cannon};
      const saved = await this.persist(library => {
        library.maps[map.identifier] ||= M.copy(plan);
        library.maps[map.identifier].guns.push(gun); M.retainPointId(library.maps[map.identifier], "gun", gun.id);
      });
      if (saved) this.selectGun(gun.id);
    }
    beginGunMove(id, kind = "gun") {
      if (!this.active || !this.editing || !this.hooks.mapReady() || !this.store?.ready || this.loadError || this.busy) return false;
      const gun = this.plan()[kind === "gun" ? "guns" : "targets"].find(point => point.id === id); if (!gun) return false;
      this.gunMove = {id, kind, mapId:this.hooks.map().identifier, point:{x:gun.x, y:gun.y}, original:{x:gun.x, y:gun.y}};
      return true;
    }
    previewGunMove(point) {if (this.gunMove && !this.busy) {this.gunMove.point = point; this.positionMarkers();}}
    cancelGunMove() {this.gunMove = null; this.positionMarkers();}
    async commitGunMove() {
      const move = this.gunMove;
      if (!move || !this.active || !this.editing || this.busy || this.hooks.map()?.identifier !== move.mapId) {this.cancelGunMove(); return;}
      if (move.point.x === move.original.x && move.point.y === move.original.y) {this.cancelGunMove(); return;}
      const saved = await this.persist(library => M.moveSavedPoint(library.maps[move.mapId], move.kind, move.id, move.point));
      this.gunMove = null; if (saved) {if (move.kind === "gun") this.selectGun(move.id); else this.selectTarget(move.id);} else this.render();
    }
    cancelTool() {this.cancelGunMove(); this.tool = null; this.cancelDraft(); this.status();}
    selectGun(id) {
      if (!this.hooks.mapReady() || this.busy) return;
      this.closeEditor(); this.gunId = id; this.targetId = null; this.tool = null;
      const gun = this.plan().guns.find(gun => gun.id === id) || null;
      this.selection = gun ? {kind:"gun", id} : null; this.hooks.mission(gun, null, null);
      if (gun && this.editing) this.editGun();
      else this.hooks.inspect?.();
      this.render(); this.status();
    }
    selectTarget(id, chooseGun = false) {
      if (!this.hooks.mapReady() || this.busy) return;
      const target = this.plan().targets.find(target => target.id === id); if (!target) return;
      if (chooseGun) {
        const settings = this.plan().configurations.filter(setting => setting.target_id === id);
        this.gunId = settings.length === 1 ? settings[0].gun_id : null;
      }
      this.selection = {kind:"target", id}; this.targetId = id; this.tool = null;
      this.closeEditor(); this.showMission(id);
      if (this.editing) this.editTarget(target);
      else this.hooks.inspect?.();
      this.render(); this.status();
    }
    showMission(id) {
      const plan = this.plan(), gun = plan.guns.find(gun => gun.id === this.gunId), target = plan.targets.find(target => target.id === id);
      const setting = M.configuration(plan, this.gunId, id);
      if (!setting) {this.hooks.mission(gun || null, null, null); return;}
      const adjusted = setting.elevation_degrees !== setting.solution.elevation_degrees || setting.fuze_seconds !== setting.solution.fuze_seconds;
      this.hooks.mission(gun, target, {...setting.solution, elevation_degrees:setting.elevation_degrees, fuze_seconds:setting.fuze_seconds,
        elevation_source:adjusted ? "saved_override" : "saved_plan", clearance_status:adjusted ? null : setting.solution.clearance_status,
        height_above_target_metres:adjusted ? null : setting.solution.height_above_target_metres});
    }
    marker(point, kind, active, click) {
      const button = document.createElement("button"); button.type = "button";
      button.className = `marker-anchor sketch-marker ${kind}${active ? " configured" : " dimmed"}`;
      button.classList.toggle("movable", this.editing);
      button.classList.toggle("selected", this.selection?.kind === kind && this.selection.id === point.id);
      button.setAttribute("data-sketch-" + kind, point.id);
      button.setAttribute("aria-label", `${label(kind)} at ${point.x}, ${point.y}`);
      button.append(globalThis.WorCalcMapMarkers.create(kind, null)); button.addEventListener("click", click);
      this.markers.push({button, point, type:kind}); return button;
    }
    render() {
      if (!this.active || !this.plan()) return;
      const plan = this.plan(), gun = plan.guns.find(gun => gun.id === this.gunId);
      this.markers = [];
      const targets = M.visibleTargets(plan, this.gunId);
      if (this.draft?.kind === "target" && !plan.targets.some(target => target.id === this.draft.point.id)) targets.push({...this.draft.point, pending:true});
      $("#sketch-layer").replaceChildren(...plan.guns.map(gun => this.marker(gun, "gun", true, () => this.selectGun(gun.id))),
        ...targets.map(target => this.marker(target, "target", Boolean(target.configuration) || target.pending, () => {
          if (target.pending) {this.selection = {kind:"target", id:target.id}; this.hooks.inspect?.();}
          else this.selectTarget(target.id, this.tool !== "target");
        })));
      $("#sketch-edit").textContent = "EDIT MODE";
      $("#sketch-edit").setAttribute("aria-pressed", String(this.editing));
      $("#sketch-view").setAttribute("aria-pressed", String(!this.editing));
      $("#sketch-view").disabled = this.busy;
      $("#sketch-toolbar").classList.toggle("editing", this.editing);
      $("#sketch-panel").classList.toggle("editing", this.editing);
      $("#sketch-edit-notice").hidden = !this.editing;
      for (const id of ["sketch-edit", "sketch-add-gun"]) $("#" + id).disabled = !this.store?.ready || Boolean(this.loadError) || this.busy;
      $("#sketch-add-gun").hidden = !this.editing; $("#sketch-add-target").hidden = !this.editing;
      $("#sketch-import").hidden = !this.editing; $("#sketch-import").disabled = !this.editing || this.busy;
      $("#sketch-add-target").disabled = !gun || this.busy;
      $("#sketch-add-gun").classList.toggle("active", this.tool === "gun"); $("#sketch-add-target").classList.toggle("active", this.tool === "target");
      const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Choose a gun";
      $("#sketch-gun-select").replaceChildren(placeholder, ...plan.guns.map(point => {
        const option = document.createElement("option"); option.value = point.id; option.textContent = `${point.cannon} · ${Math.round(point.x)}, ${Math.round(point.y)}`; return option;
      }));
      $("#sketch-gun-select").value = this.gunId || ""; $("#sketch-gun-select").disabled = this.busy;
      $("#sketch-selected-gun").textContent = gun ? gun.cannon : "No gun selected";
      $("#sketch-selected-gun").hidden = Boolean(this.draft);
      $("#sketch-count").textContent = `${plan.guns.length} guns · ${plan.targets.length} shared targets`;
      $("#sketch-state").textContent = this.editing ? "MAP EDIT · PLACE OR MOVE POINTS" : "MAP VIEW · SAVED PLAN";
      $("#workspace-title").textContent = this.editing ? "SKETCHER · EDIT MODE" : "SKETCHER · VIEW MODE";
      const outdated = M.outdatedConfigurationCount(plan);
      $("#sketch-help").textContent = this.loadError || (outdated ? `Map alignment updated. ${outdated} saved firing ${outdated === 1 ? "setting needs" : "settings need"} recalculation. Original settings are retained in the exported plan.` :
        this.editing ? "Drag any point to reposition it. Saved firing values stay unchanged." : "Select a gun to view its saved targets. Choose Edit to make changes.");
      $("#sketch-help").hidden = Boolean(this.selection) && !this.loadError && !outdated;
      $("#sketch-form").hidden = !this.editing || !this.draft; $("#sketch-editor-fields").disabled = !this.editing || this.busy || !this.store?.ready || Boolean(this.loadError);
      const choices = this.selection?.kind === "target" ? plan.configurations.filter(setting => setting.target_id === this.targetId) : [];
      $("#sketch-gun-options").hidden = !choices.length;
      $("#sketch-gun-options").replaceChildren(...choices.map(setting => {
        const owner = plan.guns.find(point => point.id === setting.gun_id);
        const button = document.createElement("button"); button.type = "button"; button.className = "sketch-target-row";
        button.classList.toggle("selected", owner.id === this.gunId);
        button.textContent = owner.cannon + " · " + Math.round(owner.x) + ", " + Math.round(owner.y) + " · " + setting.elevation_degrees.toFixed(2) + "° · " + setting.fuze_seconds.toFixed(3) + " s";
        button.addEventListener("click", () => {this.gunId = owner.id; this.selectTarget(setting.target_id);});
        return button;
      }));
      const settings = plan.configurations.filter(setting => setting.gun_id === this.gunId);
      $("#sketch-related-heading").textContent = `Related targets · ${settings.length}`;
      this.connections = this.editing || !gun ? [] : settings.map(setting => {
        const point = plan.targets.find(target => target.id === setting.target_id);
        const line = document.createElement("div"); line.className = "sketch-connection";
        return {line, gun, point};
      });
      $("#sketch-connections").replaceChildren(...this.connections.map(item => item.line));
      const selected = M.configuration(plan, this.gunId, this.targetId);
      const solution = $("#sketch-solution"); solution.hidden = this.editing || !selected;
      solution.replaceChildren();
      if (selected && !this.editing) {
        const heading = document.createElement("h3"); heading.textContent = "Saved firing solution";
        const metrics = document.createElement("div"); metrics.className = "solution-metrics";
        for (const [name, value] of [["Elevation", `${selected.elevation_degrees.toFixed(2)}°`], ["Fuze", `${selected.fuze_seconds.toFixed(3)} s`]]) {
          const metric = document.createElement("div"), caption = document.createElement("small"), number = document.createElement("b");
          caption.textContent = name; number.textContent = value; metric.append(caption, number); metrics.append(metric);
        }
        const ammo = document.createElement("p"); ammo.textContent = selected.projectile;
        solution.append(heading, metrics, ammo);
        if (selected.notes) {const notes = document.createElement("p"); notes.textContent = selected.notes; solution.append(notes);}
      }
      $("#sketch-shared-count").textContent = String(plan.targets.length);
      $("#sketch-shared-list").replaceChildren(...plan.targets.map(target => {
        const button = document.createElement("button"); button.type = "button"; button.className = "shared-target-row";
        button.classList.toggle("selected", target.id === this.targetId);
        button.textContent = `Target at ${Math.round(target.x)}, ${Math.round(target.y)}`;
        const count = document.createElement("small");
        const links = plan.configurations.filter(setting => setting.target_id === target.id).length;
        count.textContent = `${links} saved ${links === 1 ? "solution" : "solutions"}`; button.append(count);
        button.addEventListener("click", () => this.selectTarget(target.id, true)); return button;
      }));
      this.readouts = [];
      $("#sketch-readouts").replaceChildren(...(this.editing ? [] : settings.filter(setting => setting.target_id !== this.targetId).map(setting => {
        const point = plan.targets.find(target => target.id === setting.target_id);
        const chip = globalThis.WorCalcFireReadouts.create({elevation:setting.elevation_degrees, fuze:setting.fuze_seconds});
        chip.setAttribute("data-sketch-readout", point.id); chip.setAttribute("aria-label", `Elevation ${setting.elevation_degrees} degrees, fuze ${setting.fuze_seconds} seconds`);
        this.readouts.push({chip, point}); return chip;
      })));
      $("#sketch-target-list").replaceChildren(...settings.map(setting => {
        const button = document.createElement("button"); button.className = "sketch-target-row";
        button.classList.toggle("selected", this.selection?.kind === "target" && this.selection.id === setting.target_id);
        const values = document.createElement("b"); values.textContent = `${setting.elevation_degrees.toFixed(2)}° · ${setting.fuze_seconds.toFixed(3)} s`;
        const ammunition = document.createElement("small"); ammunition.textContent = setting.projectile;
        button.append(values, ammunition);
        if (setting.notes) {const notes = document.createElement("span"); notes.textContent = setting.notes; button.append(notes);}
        button.addEventListener("click", () => this.selectTarget(setting.target_id)); return button;
      }));
      $("#sketch-empty").hidden = Boolean(this.draft) || settings.length > 0;
      $("#sketch-empty").textContent = gun ? (this.editing ? "No saved targets for this gun. Add a target, or select an existing target to configure it." : "No saved targets for this gun.") : "Select a gun or target to see its details.";
      this.positionMarkers();
    }
    positionMarkers() {
      for (const {line, gun, point} of this.connections || []) {
        const start = this.hooks.position(gun), end = this.hooks.position(point);
        line.style.left = `${start.x}px`; line.style.top = `${start.y}px`;
        line.style.width = `${Math.hypot(end.x - start.x, end.y - start.y)}px`;
        line.style.transform = `rotate(${Math.atan2(end.y - start.y, end.x - start.x)}rad)`;
      }
      for (const {button, point, type} of this.markers) {
        const position = this.gunMove?.id === point.id && type === this.gunMove.kind ? this.gunMove.point : point;
        const screen = this.hooks.position(position); button.style.left = `${screen.x}px`; button.style.top = `${screen.y}px`;
      }
      const viewport = this.hooks.viewport?.(); if (!viewport) return;
      const occupied = [];
      for (const {chip, point} of this.readouts) {
        const screen = this.hooks.position(point); chip.hidden = screen.x < 0 || screen.x > viewport.width || screen.y < 0 || screen.y > viewport.height - 64;
        if (chip.hidden) continue;
        const box = globalThis.WorCalcFireReadouts.position(screen, viewport, {width:chip.offsetWidth || 190, height:chip.offsetHeight || 54}, occupied);
        chip.style.left = `${box.x}px`; chip.style.top = `${box.y}px`; occupied.push(box);
      }
    }
    openEditor(draft) {
      if (!this.active || !this.editing || this.busy) return;
      this.closeEditor(); this.draft = draft;
      $("#sketch-details-title").textContent = label(draft.kind);
      $("#sketch-x").value = draft.point.x; $("#sketch-y").value = draft.point.y;
      $("#sketch-x").max = this.plan().width; $("#sketch-y").max = this.plan().height;
      $("#sketch-editor-status").textContent = "";
      $("#sketch-delete").hidden = false; $("#sketch-delete").textContent = draft.kind === "gun" ? "DELETE GUN (Del)" : "DELETE TARGET (Del)";
      $("#sketch-form").hidden = false; this.hooks.inspect?.();
    }
    closeEditor() {if (!this.busy) {this.calculationSequence++; this.draft = null; $("#sketch-form").hidden = true;}}
    editGun() {
      const gun = this.plan().guns.find(gun => gun.id === this.gunId); if (!this.active || !this.editing || !gun || this.busy) return;
      this.openEditor({kind:"gun", point:{...gun}, mapId:this.hooks.map().identifier});
      $("#sketch-gun-fields").hidden = false; $("#sketch-gun-fields").disabled = false;
      $("#sketch-target-fields").hidden = true; $("#sketch-target-fields").disabled = true; $("#sketch-unlink").hidden = true;
      $("#sketch-weapon").replaceChildren(...Object.keys(this.hooks.options().weapons).map(value => {
        const option = document.createElement("option"); option.value = value; option.textContent = value; return option;
      }));
      $("#sketch-weapon").value = gun.cannon; $("#sketch-save").disabled = false;
      $("#sketch-editor-context").textContent = "Moving or changing cannon clears this gun's firing settings.";
    }
    editTarget(point) {
      if (!this.active || !this.editing || this.busy) return;
      const gun = this.plan().guns.find(gun => gun.id === this.gunId), existing = M.configuration(this.plan(), this.gunId, point.id);
      const previous = M.previousConfiguration(this.plan(), this.gunId, point.id), preferences = existing || previous;
      this.openEditor({kind:"target", point:{...point}, gun:gun && {...gun}, existing, solution:existing ? M.copy(existing.solution) : null, mapId:this.hooks.map().identifier});
      $("#sketch-gun-fields").hidden = true; $("#sketch-gun-fields").disabled = true;
      $("#sketch-target-fields").hidden = !gun; $("#sketch-target-fields").disabled = !gun;
      $("#sketch-unlink").hidden = !existing;
      const ammunition = gun ? this.hooks.options().weapons[gun.cannon] : [];
      $("#sketch-ammo").replaceChildren(...ammunition.map(value => {const option = document.createElement("option"); option.value = value; option.textContent = value; return option;}));
      $("#sketch-ammo").value = ammunition.includes(preferences?.projectile) ? preferences.projectile : (ammunition.includes(this.hooks.options().defaults.projectile) ? this.hooks.options().defaults.projectile : ammunition[0] || "");
      $("#sketch-burst").value = preferences?.airburst_mode ? "airburst" : "ground";
      $("#sketch-angle").value = existing?.elevation_degrees ?? ""; $("#sketch-fuze").value = existing?.fuze_seconds ?? ""; $("#sketch-notes").value = preferences?.notes || "";
      $("#sketch-editor-context").textContent = gun ? "Moving this shared point clears its firing settings." : "Select a gun for firing settings. You can edit or delete this point now.";
      $("#sketch-save").disabled = false; $("#sketch-defaults").disabled = !existing; $("#sketch-calculate").disabled = !gun;
      if (existing) {this.draft.solutionKey = this.solutionKey(this.draft, point); this.simulationText(existing.solution);}
      else $("#sketch-simulation").textContent = gun ? (previous ? "Map alignment updated. Calculate new elevation and fuze settings." : "Calculate to prepare settings for this gun.") : "No gun selected.";

    }
    readPoint(draft) {
      return {...draft.point, x:$("#sketch-x").value === "" ? NaN : Number($("#sketch-x").value), y:$("#sketch-y").value === "" ? NaN : Number($("#sketch-y").value)};
    }
    solutionKey(draft, point) {return JSON.stringify([draft.mapId, draft.gun?.id, draft.gun?.cannon, draft.gun?.x, draft.gun?.y, point.x, point.y, $("#sketch-ammo").value, $("#sketch-burst").value]);}
    simulationText(solution) {$("#sketch-simulation").textContent = `Simulator: ${solution.elevation_degrees.toFixed(2)}° · ${solution.fuze_seconds.toFixed(3)} s · ${solution.slant_range_yards.toFixed(0)} yd · ${solution.clearance_status || "clearance unknown"}`;}
    async calculateDraft(keepValues) {
      const draft = this.draft; if (!this.active || !this.editing || !draft || draft.kind !== "target" || !draft.gun || this.busy) return;
      const sequence = ++this.calculationSequence, point = this.readPoint(draft), key = this.solutionKey(draft, point);
      draft.solution = null; draft.solutionKey = null; $("#sketch-save").disabled = true; $("#sketch-defaults").disabled = true;
      $("#sketch-simulation").textContent = "Calculating…"; $("#sketch-editor-status").textContent = "";
      try {
        if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0 || point.y < 0 || point.x > this.plan().width || point.y > this.plan().height) throw Error("Target is outside the map");
        const solution = await this.hooks.calculate({map_id:draft.mapId, gun:{x:draft.gun.x,y:draft.gun.y}, target:{x:point.x,y:point.y},
          cannon:draft.gun.cannon, projectile:$("#sketch-ammo").value, method:this.hooks.options().defaults.method, calibration_mode:false, airburst_mode:$("#sketch-burst").value === "airburst"});
        if (sequence !== this.calculationSequence || this.draft !== draft) return;
        if (solution.elevation_degrees == null || solution.fuze_seconds == null) throw Error("No firing solution for this range and height");
        draft.solution = solution; draft.solutionKey = key; draft.point = point; this.simulationText(solution);
        $("#sketch-save").disabled = false; $("#sketch-defaults").disabled = false;
        if (!keepValues) this.useDefaults(); this.render();
      } catch (error) {if (sequence === this.calculationSequence && this.draft === draft) {$("#sketch-simulation").textContent = error.message; $("#sketch-editor-status").textContent = "A firing solution is required before saving this configuration.";}}
    }
    useDefaults() {if (this.active && this.editing && this.draft?.solution && !this.busy) {$("#sketch-angle").value = this.draft.solution.elevation_degrees; $("#sketch-fuze").value = this.draft.solution.fuze_seconds;}}
    async persist(change) {
      if (!this.active || !this.editing) return false;
      this.busy = true; this.render(); this.status();
      try {await this.store.update(change); this.loadError = null; return true;}
      catch (error) {$("#sketch-editor-status").textContent = `Save failed: ${error.message}`; this.hooks.status(`SAVE FAILED: ${error.message}`); return false;}
      finally {this.busy = false; this.render();}
    }
    async saveDraft() {
      const draft = this.draft; if (!this.active || !this.editing || !draft || this.busy || !this.store?.ready || this.loadError) return;
      const point = this.readPoint(draft);
      if (draft.kind === "gun") {
        const cannon = $("#sketch-weapon").value;
        const saved = await this.persist(library => {
          const plan = library.maps[draft.mapId], gun = plan.guns.find(gun => gun.id === point.id);
          M.moveGun(plan, point.id, point);
          if (gun.cannon !== cannon) plan.configurations = plan.configurations.filter(setting => setting.gun_id !== point.id);
          gun.cannon = cannon;
        });
        if (saved) this.selectGun(point.id);
      } else if (!draft.gun) {
        if (await this.persist(library => M.moveTarget(library.maps[draft.mapId], point.id, point))) this.selectTarget(point.id);
      } else {
        if (!draft.solution || draft.solutionKey !== this.solutionKey(draft, point)) await this.calculateDraft(false);
        if (!draft.solution || this.draft !== draft || draft.solutionKey !== this.solutionKey(draft, point)) return;
        const setting = {projectile:$("#sketch-ammo").value, airburst_mode:$("#sketch-burst").value === "airburst",
          elevation_degrees:$("#sketch-angle").value === "" ? NaN : Number($("#sketch-angle").value), fuze_seconds:$("#sketch-fuze").value === "" ? NaN : Number($("#sketch-fuze").value),
          notes:$("#sketch-notes").value, solution:draft.solution, updated_at:new Date().toISOString()};
        let id; const saved = await this.persist(library => {id = M.saveConfiguration(library.maps[draft.mapId], draft.gun.id, point, setting);});
        if (saved) {this.tool = null; this.selectTarget(id);}
      }
    }
    cancelDraft() {
      if (this.busy) return;
      const selection = this.selection; this.closeEditor();
      if (selection?.kind === "gun") this.selectGun(selection.id);
      else if (selection && this.plan().targets.some(target => target.id === selection.id)) this.selectTarget(selection.id);
      else {this.selection = null; this.targetId = null; this.hooks.mission(null, null, null); this.render();}
    }
    async deleteSelected() {
      const selected = this.selection; if (!this.active || !this.editing || !selected || this.busy || !this.store?.ready || this.loadError) return;
      const mapId = this.hooks.map().identifier;
      if (selected.kind === "target" && !this.plan().targets.some(point => point.id === selected.id)) {
        this.closeEditor(); this.selection = null; this.targetId = null; this.render(); this.status(); return;
      }
      this.cancelGunMove();
      const saved = await this.persist(library => {
        const plan = library.maps[mapId]; if (selected.kind === "gun") M.removeGun(plan, selected.id); else M.removeTarget(plan, selected.id);
      });
      if (saved) {
        this.closeEditor(); this.selection = null; this.targetId = null; this.tool = null;
        if (selected.kind === "gun") this.gunId = null;
        this.hooks.mission(null, null, null); this.render(); this.hooks.status(`${selected.kind.toUpperCase()} DELETED`);
      }
    }
    async unlinkSelected() {
      const draft = this.draft; if (!this.active || !this.editing || this.busy || draft?.kind !== "target" || !draft.gun) return;
      if (await this.persist(library => M.unlinkTarget(library.maps[draft.mapId], draft.gun.id, draft.point.id))) {
        this.closeEditor(); this.selection = null; this.targetId = null; this.hooks.mission(null, null, null); this.render(); this.status();
      }
    }
    async export() {
      if (!this.store?.ready || this.busy) return;
      try {await this.store.queue; this.hooks.status(await this.store.adapter.export(this.store.data));} catch (error) {this.hooks.status(`EXPORT FAILED: ${error.message}`);}
    }
    async importFile(file) {
      $("#sketch-file").value = ""; if (!this.active || !this.editing || !file || !this.store || this.busy) return;
      this.busy = true;
      try {
        if (file.size > M.MAX_BYTES) throw Error("Plan file is too large");
        const value = M.validateLibrary(JSON.parse(await file.text()), this.store.maps, this.store.options);
        const overlaps = Object.keys(value.maps).filter(id => this.store.data.maps[id]);
        if (overlaps.length && !confirm(`Replace the saved plans for ${overlaps.length} map(s) in this file? Other maps will remain.`)) {this.busy = false; return;}
        await this.store.import(value); this.loadError = null; this.busy = false; this.mapChanged(); await this.locationsChanged(); this.hooks.status("PLANS IMPORTED AND SAVED");
      } catch (error) {this.busy = false; this.hooks.status(`IMPORT FAILED: ${error.message}`);}
    }
  }
  globalThis.WorCalcSketcher = Sketcher;
})();
