// Export docs/workflow.html to docs/AI-Website-Pipeline-Guide.pdf with Chromium.
// Usage: node scripts/make_pdf.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const docs = path.resolve("docs");
const body = fs.readFileSync(path.join(docs, "workflow.html"), "utf8");
const tmp = path.join(docs, ".print.html");
// The guide is written as a page fragment; wrap it in a full document for printing (light theme).
fs.writeFileSync(tmp, `<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>${body}</body></html>`);

const browser = await chromium.launch();
const page = await browser.newPage({ colorScheme: "light" });
await page.goto("file://" + tmp, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
const out = path.join(docs, "AI-Website-Pipeline-Guide.pdf");
await page.pdf({
  path: out, format: "A4", printBackground: true,
  margin: { top: "16mm", bottom: "16mm", left: "14mm", right: "14mm" },
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: '<div style="font:9px sans-serif;color:#888;width:100%;text-align:center">AI Website Pipeline · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
});
await browser.close();
fs.unlinkSync(tmp);
console.log("Wrote " + path.relative(process.cwd(), out));
