import { cp, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const frontpage = join(root, "apps", "frontpage");
const analysis = join(root, "apps", "analysis");
const dist = join(root, "dist");

async function rewriteLegacyLinks(directory) {
  for (const entry of await readdir(directory)) {
    const path = join(directory, entry);
    const info = await stat(path);
    if (info.isDirectory()) {
      await rewriteLegacyLinks(path);
      continue;
    }
    if (!entry.endsWith(".html")) continue;

    const source = await readFile(path, "utf8");
    const output = source
      // The checked-in snapshot may have been generated for the retired Pages
      // projects. Normalize it while staging every Worker deployment.
      .replaceAll("https://curius-analysis.pages.dev", "https://curius-graph.thite.site")
      .replaceAll("https://curius.thite.site", "https://curius-links.thite.site");
    if (output !== source) await writeFile(path, output, "utf8");
  }
}

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(frontpage, join(dist, "frontpage"), { recursive: true });
await cp(analysis, join(dist, "analysis"), { recursive: true });
await rewriteLegacyLinks(dist);

console.log("Built Worker assets for the frontpage and graph sites.");
