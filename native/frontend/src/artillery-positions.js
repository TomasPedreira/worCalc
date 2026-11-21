(() => {
  // GameData.pak: Localization/english/RegimentNames.json, ui_Battery*Title.
  // Coordinates and membership remain in the bundled map catalog.
  const names = new Map([
    "Balthis", "Blackshear", "Bondurant", "Boyce", "Braxton", "Brockenbrough",
    "Brooks", "Brown", "Campbell", "Carlton", "Carpenter", "Clark", "Cook",
    "Cooper", "Courtney", "Crome", "Daquin", "Edgell", "French", "Glassie",
    "Graham", "Hexamer", "Jordan", "Lane", "Manly", "Matthews", "Maurin",
    "McGilvery", "Miller", "Owen", "Pelham", "Phillips", "Poague", "Potts",
    "Ransom", "Read", "Reily", "Reynolds", "Richardson", "Rigby", "Squires",
    "Stewart", "Thompson", "Tompkins", "Wooding",
  ].map(name => [name.toLowerCase(), `Battery ${name}`]));
  names.set("vonsehlen", "Battery Von Sehlen");
  names.set("weaver", "Battery Wever");
  names.set("philips", "Battery Phillips");
  // Walker is named in the map spawn entity, without a matching English title.
  names.set("walker", "Battery Walker");

  function label(location) {
    if (location.kind !== "battery") return null;
    const match = /_(?:Arty|Artillery)_(.+)$/i.exec(location.name || "");
    if (!match) return null;
    const token = match[1].replace(/-\d+$/, "").replace(/_Forward$/i, "").replaceAll("_", "").toLowerCase();
    return names.get(token) || null;
  }

  globalThis.WorCalcArtilleryPositions = {label};
})();
