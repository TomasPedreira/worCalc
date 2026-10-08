/* Shared map marker presentation for the calculator and saved firing plans. */
(() => {
  function create(type, name = type.toUpperCase()) {
    const marker = document.createElement("div");
    marker.className = `marker ${type}`;
    if (name != null && name !== "") {
      const label = document.createElement("span");
      label.textContent = name;
      marker.append(label);
    }
    return marker;
  }
  globalThis.WorCalcMapMarkers = Object.freeze({create});
})();
