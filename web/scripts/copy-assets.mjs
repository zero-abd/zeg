// Copies the demo assets that live elsewhere in the repo into public/, so the
// site ships the same files the README links to instead of a second copy in git.
//   docs/zeg-demo.mp4, docs/demo-poster.png  -> public/
//   services/gateway/web/demo.html            -> public/demo.html (read-only banner added)
// Runs before `next dev` and `next build`. Fails loudly if a source is missing.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(web, "..");
const pub = join(web, "public");
mkdirSync(pub, { recursive: true });

for (const f of ["zeg-demo.mp4", "demo-poster.png"]) {
    copyFileSync(join(repo, "docs", f), join(pub, f));
}

// The gateway's prepared demo, served at /demo. On the box its colophon points at the
// live client on "/"; here "/" is this landing page, so that line is replaced and a
// banner says plainly what the page is.
let html = readFileSync(join(repo, "services/gateway/web/demo.html"), "utf8");

function swap(from, to) {
    if (!html.includes(from)) {
        throw new Error(`copy-assets: expected text not found in demo.html: ${from.slice(0, 60)}`);
    }
    html = html.replace(from, to);
}

swap(
    '<body data-state="idle">',
    `<body data-state="idle">
  <div style="background:rgba(245,165,36,.08);border-bottom:1px dashed rgba(245,165,36,.45);color:#f3c583;font:500 13px/1.5 Inter,system-ui,sans-serif;padding:10px 16px;text-align:center">
    Read-only demo: pre-recorded clips and a prepared assessment. No microphone is opened and nothing you say is captured.
    The real interviewer runs on an NVIDIA GB10 box. <a href="/" style="color:#2dd4bf">Back to zeg</a>
  </div>`,
);
swap(
    'The live client is at\n      <span class="num">/</span> on the box.',
    'The live client runs on the box itself;\n      <a href="https://github.com/zero-abd/zeg#real-test-on-the-dell-box" style="color:#2dd4bf">how to run it</a>.',
);

swap('"On air \u2014 recording"', '"On air \u2014 recorded clip"');

writeFileSync(join(pub, "demo.html"), html);
console.log("copy-assets: public/zeg-demo.mp4, public/demo-poster.png, public/demo.html");
