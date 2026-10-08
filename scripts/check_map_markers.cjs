// Exercise the existing marker function with read-only database/API output.
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const root = path.resolve(__dirname, "..");
const webRequire = createRequire(path.join(root, "apps/web/package.json"));
const ts = webRequire("typescript");
require.extensions[".ts"] = (mod, file) => {
  mod._compile(
    ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
    file,
  );
};
const { buildMapMarkers } = require(
  path.join(root, "apps/web/lib/discovery.ts"),
);
const input = JSON.parse(fs.readFileSync(0, "utf8"));
function collisions(events) {
  const groups = new Map();
  for (const marker of buildMapMarkers(events)) {
    const key = `${marker.longitude},${marker.latitude}`;
    groups.set(key, [...(groups.get(key) || []), marker]);
  }
  return [...groups]
    .filter(([, markers]) => markers.length > 1)
    .map(([point, markers]) => ({ point, markers }));
}
console.log(
  JSON.stringify(
    {
      published_marker_collisions: collisions(input.all_events_for_markers),
      canonical_marker_collisions_if_published: collisions(
        input.all_canonical_map_inputs,
      ),
    },
    null,
    2,
  ),
);
