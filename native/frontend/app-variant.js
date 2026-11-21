export function appVariant(mode) {
  return ["sketcher", "kill-tracker"].includes(mode) ? mode : "calculator";
}

export function variantHtml(html, variant) {
  let result = html;
  for (const section of ["maps", "sketcher", "kill-tracker"]) {
    const include = section === "maps" ? variant !== "kill-tracker" : variant === section;
    if (!include) result = result.replace(new RegExp(`\\s*<!-- ${section}:start -->[\\s\\S]*?<!-- ${section}:end -->`, "g"), "");
  }
  const name = variant === "sketcher" ? "worSketch" : variant === "kill-tracker" ? "Kill Tracker" : "worCalc";
  return result.replace("<body>", `<body data-app-variant="${variant}">`)
    .replace("<title>worCalc</title>", `<title>${name}</title>`)
    .replace('<strong id="app-brand">WORCALC</strong>', `<strong id="app-brand">${name.toUpperCase()}</strong>`);
}
