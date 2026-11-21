export function deathMatches(death, query, scope = "all") {
  const players = scope === "killers" ? [death.killer] : scope === "victims" ? [death.victim] : [death.killer, death.victim];
  const needle = query.trim().toLowerCase();
  return players.some(player => [player?.name, player?.steam_id_64].some(value => String(value ?? "").toLowerCase().includes(needle)));
}

export function createKillTrackerController(api, update, schedule = setTimeout, cancel = clearTimeout) {
  let running = false, busy = false, timer, generation = 0;
  let deaths = [], directory = "";
  const notify = snapshot => {
    if (snapshot.directory) directory = snapshot.directory;
    // Disk capture retains every row; keep the most recent 2,000 in the live view.
    deaths = deaths.concat(snapshot.deaths).slice(-2000);
    update({...snapshot, deaths, directory, feedChanged:snapshot.feedChanged || snapshot.deaths.length > 0});
  };
  async function poll() {
    const current = generation;
    try {
      const snapshot = await api.poll();
      if (current !== generation) return;
      running = snapshot.running;
      notify(snapshot);
    } catch (error) { if (current !== generation) return; running = false; update({running:false, error:error.message, deaths, directory}); }
    if (running) timer = schedule(poll, 250);
  }
  return {
    async start(authorized) {
      if (busy || running) return;
      if (!authorized) { update({running:false,error:"Authorize read-only capture before starting.",deaths,directory}); return; }
      busy = true; generation++;
      update({running:false,busy:true,deaths,directory});
      try {
        const snapshot = await api.start(true);
        deaths = []; directory = ""; running = snapshot.running; notify({...snapshot,feedChanged:true});
        if (running) timer = schedule(poll, 250);
      } catch (error) { update({running:false,error:error.message,deaths,directory}); }
      finally {busy = false;}
    },
    async stop() {
      if (busy) return;
      busy = true; generation++; cancel(timer); timer = undefined;
      try { await api.stop(); running = false; update({running:false,deaths,directory}); }
      catch (error) { update({running,error:error.message,deaths,directory}); if (running) timer = schedule(poll,250); }
      finally { busy = false; }
    },
  };
}

export function mountKillTracker(document, api) {
  const $ = id => document.querySelector(`#${id}`);
  let deaths = [];
  function render() {
    const matches = deaths.filter(row => deathMatches(row, $("kill-search").value, $("kill-filter").value));
    $("kill-count").textContent = `${matches.length} matching events · ${deaths.length} recent events (up to 2,000)`;
    $("kill-rows").replaceChildren(...matches.slice().reverse().map(row => {
      const tr = document.createElement("tr");
      const values = [row.preexisting_at_attach ? "Earlier" : new Date(row.observed_at_ms).toLocaleTimeString(),
        row.killer.name || row.killer.steam_id_64, row.victim.name || row.victim.steam_id_64,
        `${row.cause_category} (${row.damage_type})${row.teamkill ? " · teamkill" : ""}`, row.formation];
      values.forEach(value => { const td = document.createElement("td"); td.textContent = value; tr.append(td); });
      return tr;
    }));
  }
  const controller = createKillTrackerController(api, snapshot => {
    deaths = snapshot.deaths;
    $("kill-start").disabled = snapshot.running || snapshot.busy;
    $("kill-stop").disabled = !snapshot.running;
    $("kill-authorize").disabled = snapshot.running || snapshot.busy;
    $("kill-status").textContent = snapshot.error || (snapshot.busy ? "Verifying game build…" : snapshot.running ? `${snapshot.active ? "Recorder active" : "Waiting for recorder"} · ${snapshot.buffer_size} buffer bytes` : "Capture stopped.");
    $("kill-output").textContent = snapshot.directory ? `Saved capture: ${snapshot.directory}` : "";
    if (snapshot.feedChanged) render();
  });
  $("kill-start").focus();
  render();
  $("kill-start").addEventListener("click", () => controller.start($("kill-authorize").checked));
  $("kill-stop").addEventListener("click", () => controller.stop());
  $("kill-search").addEventListener("input", render);
  $("kill-filter").addEventListener("change", render);
}
