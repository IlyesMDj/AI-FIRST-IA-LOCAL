// Runs `next <args>` for production with a dedicated output dir (.next-prod, so a
// running `next dev` using .next is never clobbered) and telemetry forced off.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const nextBin = require.resolve("next/dist/bin/next");
const env = { ...process.env, NEXT_DIST_DIR: process.env.NEXT_DIST_DIR || ".next-prod", NEXT_TELEMETRY_DISABLED: "1" };
const child = spawn(process.execPath, [nextBin, ...process.argv.slice(2)], { stdio: "inherit", env });
child.on("exit", (code) => process.exit(code ?? 1));
