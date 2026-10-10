import { cp, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const source = new URL("../.agents/skills/", import.meta.url);
const destination = new URL("../.claude/skills/", import.meta.url);

for (const entry of await readdir(source, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  await cp(
    fileURLToPath(new URL(`${entry.name}/`, source)),
    fileURLToPath(new URL(`${entry.name}/`, destination)),
    { recursive: true },
  );
  console.log(`Synced ${entry.name} for Claude Code`);
}
