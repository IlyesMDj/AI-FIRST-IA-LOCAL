// Lists UI strings (t("…") and N_("…")) that have no French translation.
// Usage: node scripts/check-i18n.mjs [--list]   (exit code 1 when something is missing)
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const DIRS = ["app", "components", "lib"];
const KEY_RE = /\b(?:t|N_|translate\(getLang\(\),)\s*\(?\s*"((?:[^"\\]|\\.)*)"/g;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|mjs)$/.test(name) && !name.startsWith("i18n-fr")) out.push(p);
  }
  return out;
}

const keys = new Map();
for (const d of DIRS) {
  for (const file of walk(join(ROOT, d))) {
    const src = readFileSync(file, "utf8");
    for (const m of src.matchAll(KEY_RE)) {
      const key = JSON.parse(`"${m[1]}"`);
      if (!keys.has(key)) keys.set(key, file.slice(ROOT.length));
    }
  }
}
// Plain constants translated dynamically elsewhere (UNREACHABLE message in lib/api.ts).
const api = readFileSync(join(ROOT, "lib", "api.ts"), "utf8").match(/const UNREACHABLE = "([^"]+)"/);
if (api) keys.set(api[1], "lib/api.ts");

const frSrc = readFileSync(join(ROOT, "lib", "i18n-fr.ts"), "utf8");
const frKeys = new Set([...frSrc.matchAll(/^\s*"((?:[^"\\]|\\.)*)"\s*:/gm)].map((m) => JSON.parse(`"${m[1]}"`)));

if (process.argv.includes("--list")) {
  for (const k of keys.keys()) console.log(JSON.stringify(k));
  process.exit(0);
}
const missing = [...keys].filter(([k]) => !frKeys.has(k));
const unused = [...frKeys].filter((k) => !keys.has(k));
for (const [k, f] of missing) console.log(`MISSING  ${f}: ${JSON.stringify(k)}`);
for (const k of unused) console.log(`UNUSED   ${JSON.stringify(k)}`);
console.log(`${keys.size} keys, ${missing.length} missing, ${unused.length} unused`);
process.exit(missing.length ? 1 : 0);
