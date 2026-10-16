#!/usr/bin/env node
// Fails the build if user-facing copy uses phrases that imply Proofly verified a
// listing or that it is safe to pay. Scan app/components/lib text, not this file.

import { readdir, readFile } from "node:fs/promises";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const SCAN_DIRS = ["app", "components", "lib"];
const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs"]);

const FORBIDDEN = [
  { re: /\bverified listing\b/i, label: "verified listing" },
  { re: /\bsafe to pay\b/i, label: "safe to pay" },
  { re: /\ball clear\b/i, label: "all clear" },
  { re: /\bscam[- ]free\b/i, label: "scam-free" },
];

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") continue;
      files.push(...(await walk(path)));
    } else if (EXTENSIONS.has(extname(entry.name))) {
      files.push(path);
    }
  }
  return files;
}

const files = (await Promise.all(SCAN_DIRS.map((d) => walk(join(ROOT, d))))).flat();
const hits = [];

for (const file of files) {
  const text = await readFile(file, "utf8");
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    for (const { re, label } of FORBIDDEN) {
      if (re.test(lines[i])) {
        hits.push(`${relative(ROOT, file)}:${i + 1}  forbidden phrase "${label}"`);
      }
    }
  }
}

if (hits.length > 0) {
  console.error("False-assurance copy found:\n" + hits.map((h) => `  ${h}`).join("\n"));
  process.exit(1);
}

console.log(`check-copy: ok (${files.length} files)`);
