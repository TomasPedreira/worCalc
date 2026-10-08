/* The calculator and saved plans share the same elevation/fuze window. */
(() => {
  const elevationText = value => value == null ? "No solution" : `${value.toFixed(2)}°`;
  const fuzeText = value => value == null ? "—" : `${value.toFixed(3)} s`;
  function create({elevation, fuze, label = "ELEVATION", ids = {}} = {}) {
    const window = document.createElement("div"); window.className = "range-chip";
    function metric(heading, value, headingId, valueId) {
      const column = document.createElement("div"), small = document.createElement("small"), number = document.createElement("b");
      small.textContent = heading; number.textContent = value;
      if (headingId) small.id = headingId;
      if (valueId) number.id = valueId;
      column.append(small, number); return column;
    }
    const separator = document.createElement("span"); separator.setAttribute("aria-hidden", "true");
    window.append(metric(label, elevationText(elevation), ids.elevationLabel, ids.elevation), separator,
      metric("FUZE", fuzeText(fuze), null, ids.fuze));
    return window;
  }
  function position(point, viewport, size, occupied = []) {
    const margin = 8, bottom = 64;
    const clamp = (value, max) => Math.max(margin, Math.min(max - margin, value));
    const candidates = [
      {x:point.x + 24, y:point.y - size.height - 12},
      {x:point.x - size.width - 24, y:point.y - size.height - 12},
      {x:point.x + 24, y:point.y + 24},
      {x:point.x - size.width - 24, y:point.y + 24},
    ].map(box => ({x:clamp(box.x, viewport.width - size.width), y:clamp(box.y, viewport.height - bottom - size.height), ...size}));
    const overlap = box => occupied.reduce((total, other) => total +
      Math.max(0, Math.min(box.x + box.width, other.x + other.width) - Math.max(box.x, other.x)) *
      Math.max(0, Math.min(box.y + box.height, other.y + other.height) - Math.max(box.y, other.y)), 0);
    return candidates.reduce((best, candidate) => overlap(candidate) < overlap(best) ? candidate : best);
  }
  globalThis.WorCalcFireReadouts = Object.freeze({create, elevationText, fuzeText, position});
})();
