// Compila cada bloque ```mermaid de los .md del repositorio con mermaid-cli
// (E2-M9b). Sale con codigo 1 si alguno no compila.
//
//   cd tools/mermaid && npm install && node check-mermaid.mjs
//
// Usa el Chrome instalado (CHROME_PATH) y comparte un solo navegador para todos
// los bloques. Solo desarrollo: no entra en ninguna imagen.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";
import { renderMermaid } from "@mermaid-js/mermaid-cli";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SKIP = new Set(["node_modules", ".git", ".venv", "venv", "staticfiles", "__pycache__", ".pytest_cache"]);
const BLOCK = /```mermaid\r?\n([\s\S]*?)```/g;

function markdownFiles(dir) {
  const found = [];
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      found.push(...markdownFiles(path));
    } else if (name.endsWith(".md")) {
      found.push(path);
    }
  }
  return found;
}

function lineOf(text, index) {
  return text.slice(0, index).split("\n").length;
}

const blocks = [];
for (const file of markdownFiles(ROOT)) {
  const text = readFileSync(file, "utf-8");
  for (const match of text.matchAll(BLOCK)) {
    blocks.push({ file: relative(ROOT, file).replace(/\\/g, "/"), line: lineOf(text, match.index), definition: match[1] });
  }
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-first-run"] });
let failed = 0;
try {
  for (const block of blocks) {
    try {
      await renderMermaid(browser, block.definition, "svg", { mermaidConfig: { securityLevel: "strict" } });
      console.log(`OK    ${block.file}:${block.line}`);
    } catch (error) {
      failed += 1;
      console.log(`FALLA ${block.file}:${block.line}\n      ${String(error.message || error).split("\n").slice(0, 3).join("\n      ")}`);
    }
  }
} finally {
  await browser.close();
}
console.log(`\n${blocks.length - failed} de ${blocks.length} bloques Mermaid compilan.`);
process.exit(failed || !blocks.length ? 1 : 0);
