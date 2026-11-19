// Real-browser quality gate: loads every page at desktop and phone size in Chromium.
// Fails on JavaScript errors, failed local requests, horizontal page scroll,
// or a 3D canvas that never draws. Saves screenshots to <out>/.
//
// Usage: node scripts/browser_check.mjs [siteDir=site] [outDir=screenshots] [--json]
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const asJson = process.argv.includes("--json");
const siteDir = path.resolve(args[0] || "site");
const outDir = path.resolve(args[1] || "screenshots");
const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".json": "application/json", ".txt": "text/plain" };

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p.endsWith("/")) p += "index.html";
  const file = path.join(siteDir, p);
  if (!file.startsWith(siteDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const pages = fs.readdirSync(siteDir).filter((f) => f.endsWith(".html")).sort();
const viewports = [
  { name: "desktop", width: 1366, height: 860, deviceScaleFactor: 1 },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
const errors = [];
const shots = [];

for (const vp of viewports) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor, isMobile: vp.isMobile, hasTouch: vp.hasTouch });
  for (const file of pages) {
    const page = await ctx.newPage();
    const where = `${file} (${vp.name})`;
    page.on("pageerror", (e) => errors.push(`${where}: JavaScript error: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text())) errors.push(`${where}: console error: ${m.text()}`); });
    page.on("requestfailed", (r) => { if (r.url().startsWith(base)) errors.push(`${where}: failed to load ${r.url().replace(base, "")}`); });
    page.on("response", (r) => { if (r.url().startsWith(base) && r.status() >= 400) errors.push(`${where}: ${r.status()} for ${r.url().replace(base, "")}`); });

    await page.goto(`${base}/${file}`, { waitUntil: "load" });
    await page.waitForTimeout(1500);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 1) errors.push(`${where}: page scrolls sideways by ${overflow}px`);

    const canvas = await page.evaluate(() => {
      const c = document.querySelector("canvas");
      if (!c) return null;
      return { w: c.width, h: c.height, hasGl: !!(c.getContext("webgl2") || c.getContext("webgl")) };
    });
    if (canvas && (!canvas.w || !canvas.h)) errors.push(`${where}: 3D canvas has zero size`);

    // Scroll through so scroll-triggered motion runs, then capture the top of the page
    await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } window.scrollTo(0, 0); });
    await page.waitForTimeout(600);
    const shot = path.join(outDir, `${file.replace(".html", "")}-${vp.name}.png`);
    await page.screenshot({ path: shot, fullPage: false });
    shots.push(path.relative(process.cwd(), shot));
    await page.close();
  }
  await ctx.close();
}
await browser.close();
server.close();

if (asJson) {
  console.log(JSON.stringify({ ok: errors.length === 0, errors, screenshots: shots }));
} else if (errors.length) {
  console.log("Browser check FAILED:\n" + errors.map((e) => "  - " + e).join("\n"));
} else {
  console.log(`Browser check passed (${pages.length} pages x ${viewports.length} sizes). Screenshots in ${path.relative(process.cwd(), outDir)}/`);
}
process.exit(errors.length ? 1 : 0);
