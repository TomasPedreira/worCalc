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
      $("#sketch-import").addEventListener("click", () => $("#sketch-file").click());
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
        this.selection ? "SELECTED DETAILS ON THE RIGHT · SAVE CHANGES · DEL TO DELETE" : "SELECT A GUN OR TARGET · DEL DELETES THE SELECTED POINT"));
    }
    toggleEdit() {
      if (this.busy || !this.store?.ready || this.loadError) return;
      this.cancelGunMove(); this.editing = !this.editing; this.tool = null;
      if (!this.editing && this.targetId && M.configuration(this.plan(), this.gunId, this.targetId)) this.showMission(this.targetId);
      this.render(); this.status();
    }
    setTool(tool) {
      if (this.busy || !this.store?.ready || this.loadError || (tool === "target" && !this.gunId)) return;
      this.editing = true; this.cancelGunMove();
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
    beginGunMove(id) {
      if (!this.active || !this.editing || !this.hooks.mapReady() || !this.store?.ready || this.loadError || this.busy) return false;
      const gun = this.plan().guns.find(gun => gun.id === id); if (!gun) return false;
      this.selectGun(id);
      this.gunMove = {id, mapId:this.hooks.map().identifier, point:{x:gun.x, y:gun.y}, original:{x:gun.x, y:gun.y}};
      return true;
    }
    previewGunMove(point) {if (this.gunMove && !this.busy) {this.gunMove.point = point; this.positionMarkers();}}
    cancelGunMove() {this.gunMove = null; this.positionMarkers();}
    async commitGunMove() {
      const move = this.gunMove;
      if (!move || !this.editing || this.busy || this.hooks.map()?.identifier !== move.mapId) {this.cancelGunMove(); return;}
      if (move.point.x === move.original.x && move.point.y === move.original.y) {this.cancelGunMove(); return;}
      const saved = await this.persist(library => M.moveGun(library.maps[move.mapId], move.id, move.point));
      this.gunMove = null; if (saved) this.selectGun(move.id); else this.render();
    }
    cancelTool() {this.cancelGunMove(); this.tool = null; this.cancelDraft(); this.status();}
    selectGun(id) {
      if (!this.hooks.mapReady() || this.busy) return;
      this.closeEditor(); this.gunId = id; this.targetId = null; this.tool = null;
      const gun = this.plan().guns.find(gun => gun.id === id) || null;
      this.selection = gun ? {kind:"gun", id} : null; this.hooks.mission(gun, null, null);
      if (gun) this.editGun(); this.render(); this.status();
    }
    selectTarget(id) {
      if (!this.hooks.mapReady() || this.busy) return;
      const target = this.plan().targets.find(target => target.id === id); if (!target) return;
      this.selection = {kind:"target", id}; this.targetId = id; this.tool = null;
      this.showMission(id); this.editTarget(target); this.render(); this.status();
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
          else this.selectTarget(target.id);
        })));
      $("#sketch-edit").textContent = this.editing ? "DONE EDITING" : "EDIT";
      for (const id of ["sketch-edit", "sketch-add-gun"]) $("#" + id).disabled = !this.store?.ready || Boolean(this.loadError) || this.busy;
      $("#sketch-add-gun").hidden = false; $("#sketch-add-target").hidden = !this.editing;
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
      $("#sketch-help").textContent = this.loadError || "Select a point to edit · Save applies changes · Del deletes selection.";
      $("#sketch-help").hidden = Boolean(this.selection) && !this.loadError;
      $("#sketch-form").hidden = !this.draft; $("#sketch-editor-fields").disabled = this.busy || !this.store?.ready || Boolean(this.loadError);
      const settings = plan.configurations.filter(setting => setting.gun_id === this.gunId);
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
        button.append(values, ammunition); button.addEventListener("click", () => this.selectTarget(setting.target_id)); return button;
      }));
      $("#sketch-empty").hidden = Boolean(this.draft) || settings.length > 0;
      $("#sketch-empty").textContent = gun ? "No saved targets for this gun. Add a target, or select an existing target to configure it." : "Select a gun or target to see its details.";
      this.positionMarkers();
    }
    positionMarkers() {
      for (const {button, point, type} of this.markers) {
        const position = this.gunMove?.id === point.id && type === "gun" ? this.gunMove.point : point;
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
      const gun = this.plan().guns.find(gun => gun.id === this.gunId); if (!gun || this.busy) return;
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
      if (this.busy) return;
      const gun = this.plan().guns.find(gun => gun.id === this.gunId), existing = M.configuration(this.plan(), this.gunId, point.id);
      this.openEditor({kind:"target", point:{...point}, gun:gun && {...gun}, existing, solution:existing ? M.copy(existing.solution) : null, mapId:this.hooks.map().identifier});
      $("#sketch-gun-fields").hidden = true; $("#sketch-gun-fields").disabled = true;
      $("#sketch-target-fields").hidden = false; $("#sketch-target-fields").disabled = !gun;
      $("#sketch-unlink").hidden = !existing;
      const ammunition = gun ? this.hooks.options().weapons[gun.cannon] : [];
      $("#sketch-ammo").replaceChildren(...ammunition.map(value => {const option = document.createElement("option"); option.value = value; option.textContent = value; return option;}));
      $("#sketch-ammo").value = existing?.projectile || (ammunition.includes(this.hooks.options().defaults.projectile) ? this.hooks.options().defaults.projectile : ammunition[0] || "");
      $("#sketch-burst").value = existing?.airburst_mode ? "airburst" : "ground";
      $("#sketch-angle").value = existing?.elevation_degrees ?? ""; $("#sketch-fuze").value = existing?.fuze_seconds ?? ""; $("#sketch-notes").value = existing?.notes || "";
      $("#sketch-editor-context").textContent = gun ? "Moving this shared point clears its firing settings." : "Select a gun for firing settings. You can edit or delete this point now.";
      $("#sketch-save").disabled = false; $("#sketch-defaults").disabled = !existing; $("#sketch-calculate").disabled = !gun;
      if (existing) {this.draft.solutionKey = this.solutionKey(this.draft, point); this.simulationText(existing.solution);}
      else $("#sketch-simulation").textContent = gun ? "Calculate to prepare settings for this gun." : "No gun selected.";
      if (!existing && gun && this.editing) this.calculateDraft(false);
    }
    readPoint(draft) {
      return {...draft.point, x:$("#sketch-x").value === "" ? NaN : Number($("#sketch-x").value), y:$("#sketch-y").value === "" ? NaN : Number($("#sketch-y").value)};
    }
    solutionKey(draft, point) {return JSON.stringify([draft.mapId, draft.gun?.id, draft.gun?.cannon, draft.gun?.x, draft.gun?.y, point.x, point.y, $("#sketch-ammo").value, $("#sketch-burst").value]);}
    simulationText(solution) {$("#sketch-simulation").textContent = `Simulator: ${solution.elevation_degrees.toFixed(2)}° · ${solution.fuze_seconds.toFixed(3)} s · ${solution.slant_range_yards.toFixed(0)} yd · ${solution.clearance_status || "clearance unknown"}`;}
    async calculateDraft(keepValues) {
      const draft = this.draft; if (!draft || draft.kind !== "target" || !draft.gun || this.busy) return;
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
    useDefaults() {if (this.draft?.solution && !this.busy) {$("#sketch-angle").value = this.draft.solution.elevation_degrees; $("#sketch-fuze").value = this.draft.solution.fuze_seconds;}}
    async persist(change) {
      this.busy = true; this.render(); this.status();
      try {await this.store.update(change); this.loadError = null; return true;}
      catch (error) {$("#sketch-editor-status").textContent = `Save failed: ${error.message}`; this.hooks.status(`SAVE FAILED: ${error.message}`); return false;}
      finally {this.busy = false; this.render();}
    }
    async saveDraft() {
      const draft = this.draft; if (!draft || this.busy || !this.store?.ready || this.loadError) return;
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
      const selected = this.selection; if (!this.active || !selected || this.busy || !this.store?.ready || this.loadError) return;
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
      const draft = this.draft; if (this.busy || draft?.kind !== "target" || !draft.gun) return;
      if (await this.persist(library => M.unlinkTarget(library.maps[draft.mapId], draft.gun.id, draft.point.id))) {
        this.closeEditor(); this.selection = null; this.targetId = null; this.hooks.mission(null, null, null); this.render(); this.status();
      }
    }
    async export() {
      if (!this.store?.ready || this.busy) return;
      try {await this.store.queue; this.hooks.status(await this.store.adapter.export(this.store.data));} catch (error) {this.hooks.status(`EXPORT FAILED: ${error.message}`);}
    }
    async importFile(file) {
      $("#sketch-file").value = ""; if (!file || !this.store || this.busy) return;
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
