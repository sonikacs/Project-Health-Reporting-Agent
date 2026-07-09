import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const SLIDE = { width: 1280, height: 720 };
const PAGE = { left: 54, top: 42, width: 1172, height: 620 };
const COLORS = {
  ink: "#000000",
  muted: "#555555",
  rule: "#B8BCC4",
  panel: "#EDEDED",
  canvas: "#FFFFFF",
  red: "#C62828",
  amber: "#F59E0B",
  green: "#2E7D32",
};

const args = parseArgs(process.argv.slice(2));
const inputRoot = args.input || args._[0] || "outputs/weekly";
const month = args.month || currentMonth();
const outputPath = args.output || args._[1] || `outputs/monthly/${month}/project_health_monthly_synthesis.pptx`;
const previewDir = args.previewDir || args._[2] || `outputs/monthly/${month}/preview`;
const logDir = args.logDir || "logs";
let logPath = "";

/** Parse positional and named CLI arguments. */
function parseArgs(argv) {
  const parsed = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith("--")) {
      parsed._.push(item);
      continue;
    }
    const key = item.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      parsed[key] = true;
      continue;
    }
    parsed[key] = value;
    index += 1;
  }
  return parsed;
}

/** Return the current month in YYYY-MM format. */
function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

/** Write a structured monthly-generation log message to console and file. */
async function writeLogEntry(level, message, meta = {}) {
  const line = `${new Date().toISOString()} ${level.toUpperCase()} monthly_presentation - ${message}${
    Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : ""
  }\n`;
  if (logPath) await fs.appendFile(logPath, line, "utf8");
  process.stdout.write(line);
}

/** Persist an artifact-tool Blob to disk. */
async function writeBlobToFile(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

/** Read weekly health JSON reports from an input directory. */
function readReports(inputDir, files) {
  return Promise.all(
    files
      .filter((file) => file.endsWith("_weekly_health.json"))
      .map(async (file) => JSON.parse(await fs.readFile(path.join(inputDir, file), "utf8"))),
  );
}

/** Return whether a path exists and is a directory. */
async function directoryExists(dir) {
  try {
    return (await fs.stat(dir)).isDirectory();
  } catch {
    return false;
  }
}

/** Return whether a directory contains weekly health JSON reports. */
async function hasWeeklyReports(dir) {
  if (!(await directoryExists(dir))) return false;
  const files = await fs.readdir(dir);
  return files.some((file) => file.endsWith("_weekly_health.json"));
}

/** Resolve the weekly input folder, preferring the latest dated child run. */
async function resolveInputDir(root) {
  if (!(await directoryExists(root))) {
    throw new Error(`Weekly input directory does not exist: ${root}`);
  }

  const entries = await fs.readdir(root, { withFileTypes: true });
  const datedDirs = entries
    .filter((entry) => entry.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(entry.name))
    .map((entry) => path.join(root, entry.name))
    .sort()
    .reverse();
  for (const dir of datedDirs) {
    if (await hasWeeklyReports(dir)) return dir;
  }
  if (await hasWeeklyReports(root)) return root;
  throw new Error(`No weekly health JSON reports found in ${root} or dated child folders.`);
}

/** Add a styled editable text box to a slide. */
function addTextBox(slide, value, position, style = {}) {
  const box = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  box.text = value;
  box.text.style = {
    fontSize: style.fontSize || 22,
    color: style.color || COLORS.ink,
    bold: style.bold || false,
    alignment: style.alignment || "left",
  };
  return box;
}

/** Add a neutral rectangular panel to a slide. */
function addPanel(slide, position, fill = COLORS.panel) {
  return slide.shapes.add({
    geometry: "rect",
    position,
    fill,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

/** Add a thin horizontal rule to separate slide regions. */
function addHorizontalRule(slide, left, top, width) {
  slide.shapes.add({
    geometry: "rect",
    position: { left, top, width, height: 1.5 },
    fill: COLORS.rule,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

/** Add a standard footer and page number. */
function addStandardFooter(slide, pageNumber) {
  addTextBox(slide, "Project Health Reporting Agent", { left: PAGE.left, top: 668, width: 360, height: 24 }, { fontSize: 13, color: COLORS.muted, bold: true });
  addTextBox(slide, String(pageNumber).padStart(2, "0"), { left: 1182, top: 668, width: 44, height: 24 }, { fontSize: 13, color: COLORS.muted, bold: true, alignment: "right" });
}

/** Add a standard slide title, optional subtitle, rule, and footer. */
function addSlideHeader(slide, value, subtitle, pageNumber) {
  addTextBox(slide, value, { left: PAGE.left, top: PAGE.top, width: 920, height: 86 }, { fontSize: 42, bold: true });
  if (subtitle) {
    addTextBox(slide, subtitle, { left: PAGE.left, top: 132, width: 900, height: 42 }, { fontSize: 18, color: COLORS.muted });
  }
  addHorizontalRule(slide, PAGE.left, 190, PAGE.width);
  addStandardFooter(slide, pageNumber);
}

/** Return the display color for a RAG value. */
function getRagColor(rag) {
  if (rag === "Red") return COLORS.red;
  if (rag === "Amber") return COLORS.amber;
  return COLORS.green;
}

/** Format a decimal percentage for slide labels. */
function formatPercentage(value) {
  if (value === null || value === undefined) return "n/a";
  return `${Math.round(Number(value) * 100)}%`;
}

/** Calculate portfolio-level summary metrics from weekly reports. */
function summarizePortfolioMetrics(reports) {
  const counts = { Red: 0, Amber: 0, Green: 0 };
  for (const report of reports) counts[report.rag] = (counts[report.rag] || 0) + 1;
  return {
    counts,
    avgScore: Math.round(reports.reduce((sum, r) => sum + r.score, 0) / reports.length),
    activeTasks: reports.reduce((sum, r) => sum + r.metrics.active_tasks, 0),
    riskyActive: reports.reduce((sum, r) => sum + r.metrics.red_yellow_active_tasks, 0),
    overdue: reports.reduce((sum, r) => sum + r.metrics.overdue_open_tasks, 0),
    nearTerm: reports.reduce((sum, r) => sum + r.metrics.near_term_risky_tasks, 0),
    blockers: reports.reduce((sum, r) => sum + r.metrics.blocker_comment_count, 0),
    onHold: reports.reduce((sum, r) => sum + r.metrics.on_hold_tasks, 0),
  };
}

/** Add a large metric and label pair to a slide. */
function addMetric(slide, x, y, value, label, color = COLORS.ink) {
  addTextBox(slide, value, { left: x, top: y, width: 180, height: 72 }, { fontSize: 54, bold: true, color });
  addTextBox(slide, label, { left: x, top: y + 78, width: 210, height: 52 }, { fontSize: 18, color: COLORS.muted });
}

/** Add square-bullet text items with consistent spacing. */
function addBullets(slide, items, x, y, width, gap = 78) {
  items.forEach((item, index) => {
    const top = y + index * gap;
    slide.shapes.add({
      geometry: "rect",
      position: { left: x, top: top + 7, width: 9, height: 9 },
      fill: COLORS.ink,
      line: { style: "solid", fill: "none", width: 0 },
    });
    addTextBox(slide, item, { left: x + 28, top, width, height: gap - 8 }, { fontSize: 19, color: COLORS.ink });
  });
}

/** Convert a full project name into a concise slide label. */
function getProjectShortName(name) {
  if (name.includes("UniSan")) return "UniSan";
  if (name.includes("Titan")) return "Titan";
  return name.replace("Zycus - ", "").replace(" S2P Implementation", "");
}

/** Build the six-slide monthly executive synthesis deck. */
function buildMonthlySynthesisDeck(reports) {
  const summary = summarizePortfolioMetrics(reports);
  const presentation = Presentation.create({ slideSize: SLIDE });

  let slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  addTextBox(slide, "Monthly Health Synthesis", { left: PAGE.left, top: 86, width: 720, height: 130 }, { fontSize: 58, bold: true });
  addTextBox(slide, "S2P implementation portfolio | July 2026", { left: PAGE.left, top: 232, width: 640, height: 42 }, { fontSize: 24, color: COLORS.muted });
  addPanel(slide, { left: 824, top: 78, width: 350, height: 490 });
  addMetric(slide, 870, 136, String(reports.length), "projects analyzed");
  addMetric(slide, 870, 294, String(summary.counts.Red), "projects currently Red", COLORS.red);
  addMetric(slide, 870, 452, String(summary.avgScore), "average risk score");
  addTextBox(slide, "The portfolio needs recovery governance now, not just routine status reporting.", { left: PAGE.left, top: 406, width: 650, height: 104 }, { fontSize: 30, bold: true });
  addStandardFooter(slide, 1);

  slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  addSlideHeader(slide, "Both projects are Red, but for different reasons", "The portfolio pattern is not one generic delay. UniSan has summary-level schedule distress; Titan has execution and dependency risk beneath a Green summary health flag.", 2);
  const cardW = 550;
  reports.forEach((report, i) => {
    const x = PAGE.left + i * (cardW + 58);
    addPanel(slide, { left: x, top: 230, width: cardW, height: 330 });
    addTextBox(slide, getProjectShortName(report.project_name), { left: x + 28, top: 256, width: 230, height: 44 }, { fontSize: 30, bold: true });
    addTextBox(slide, report.rag, { left: x + 390, top: 254, width: 100, height: 44 }, { fontSize: 30, bold: true, color: getRagColor(report.rag), alignment: "right" });
    addTextBox(slide, `${report.score}/100 risk score`, { left: x + 28, top: 314, width: 230, height: 30 }, { fontSize: 18, color: COLORS.muted });
    addBullets(slide, report.top_reasons.slice(0, 3), x + 28, 372, 470, 58);
  });

  slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  addSlideHeader(slide, "The common trend is near-term execution pressure", "Across both plans, the highest shared signal is not budget. It is schedule execution risk concentrated in near-term and overdue work.", 3);
  slide.charts.add("bar", {
    position: { left: PAGE.left, top: 245, width: 710, height: 330 },
    categories: reports.map((report) => getProjectShortName(report.project_name)),
    series: [
      { name: "Overdue open tasks", values: reports.map((r) => r.metrics.overdue_open_tasks), fill: COLORS.red },
      { name: "Near-term risky tasks", values: reports.map((r) => r.metrics.near_term_risky_tasks), fill: COLORS.amber },
    ],
    hasLegend: true,
    dataLabels: { showValue: true, position: "outEnd" },
    yAxis: { majorGridlines: { style: "solid", fill: COLORS.rule, width: 1 } },
  });
  addPanel(slide, { left: 830, top: 245, width: 360, height: 330 });
  addMetric(slide, 866, 284, String(summary.overdue), "open tasks are already overdue", COLORS.red);
  addMetric(slide, 866, 436, String(summary.nearTerm), "near-term tasks need attention", COLORS.amber);

  slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  addSlideHeader(slide, "Emerging risks point to dependencies and data readiness", "The comments and evidence rows show external inputs, mappings, workshops, and configuration tasks as the leading sources of delivery risk.", 4);
  const themes = [
    ["Dependency risk", "Client or integration inputs are pending, including sample data, field mapping, and workflow details."],
    ["Milestone compression", "Many tasks due within the next reporting window are incomplete or already marked Red/Yellow."],
    ["Plan quality gap", "Budget burn and target dates are unavailable or unparseable, reducing executive confidence in commercial health."],
  ];
  themes.forEach((theme, i) => {
    const x = PAGE.left + i * 390;
    addPanel(slide, { left: x, top: 250, width: 340, height: 250 });
    addTextBox(slide, theme[0], { left: x + 24, top: 278, width: 292, height: 42 }, { fontSize: 25, bold: true });
    addTextBox(slide, theme[1], { left: x + 24, top: 352, width: 292, height: 116 }, { fontSize: 19, color: COLORS.ink });
  });

  slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  addSlideHeader(slide, "Project-level evidence supports executive escalation", "The strongest risks are visible in the generated weekly reports, not inferred from a black-box model.", 5);
  const startY = 250;
  addTextBox(slide, "Project", { left: PAGE.left, top: 214, width: 160, height: 28 }, { fontSize: 16, color: COLORS.muted, bold: true });
  addTextBox(slide, "RAG", { left: 240, top: 214, width: 90, height: 28 }, { fontSize: 16, color: COLORS.muted, bold: true });
  addTextBox(slide, "Key evidence", { left: 360, top: 214, width: 600, height: 28 }, { fontSize: 16, color: COLORS.muted, bold: true });
  addTextBox(slide, "Recommended focus", { left: 970, top: 214, width: 240, height: 28 }, { fontSize: 16, color: COLORS.muted, bold: true });
  addHorizontalRule(slide, PAGE.left, 244, PAGE.width);
  reports.forEach((report, i) => {
    const y = startY + i * 155;
    addTextBox(slide, getProjectShortName(report.project_name), { left: PAGE.left, top: y, width: 160, height: 36 }, { fontSize: 24, bold: true });
    addTextBox(slide, report.rag, { left: 240, top: y, width: 90, height: 36 }, { fontSize: 24, bold: true, color: getRagColor(report.rag) });
    addTextBox(slide, report.top_reasons.slice(0, 2).join(" "), { left: 360, top: y, width: 560, height: 84 }, { fontSize: 18 });
    addTextBox(slide, report.recommendations[0], { left: 970, top: y, width: 230, height: 88 }, { fontSize: 18 });
    addHorizontalRule(slide, PAGE.left, y + 116, PAGE.width);
  });

  slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  addSlideHeader(slide, "Recommended action is a two-week recovery cadence", "The next cycle should turn risk evidence into owned actions, updated dates, and cleaner executive reporting.", 6);
  addBullets(
    slide,
    [
      "Hold a recovery review for Red items with PMs, delivery leads, and client owners.",
      "Create a 14-day action plan for overdue and near-term risky tasks.",
      "Convert blocker comments into named actions with owner, due date, and escalation path.",
      "Add budget and burn-rate fields so commercial health can be scored in the next monthly report.",
    ],
    PAGE.left,
    250,
    760,
    76,
  );
  addPanel(slide, { left: 890, top: 260, width: 300, height: 260 });
  addTextBox(slide, "Executive ask", { left: 924, top: 292, width: 230, height: 40 }, { fontSize: 26, bold: true });
  addTextBox(slide, "Approve a weekly recovery cadence until both projects return to Amber with dated mitigation plans.", { left: 924, top: 360, width: 230, height: 124 }, { fontSize: 21 });

  return presentation;
}

/** Run the monthly deck generation workflow. */
async function main() {
  await fs.mkdir(logDir, { recursive: true });
  logPath = path.join(logDir, `monthly_presentation_${month}.log`);
  await writeLogEntry("info", "Starting monthly presentation generation", { inputRoot, outputPath, previewDir, month });

  const inputDir = await resolveInputDir(inputRoot);
  await writeLogEntry("info", "Resolved weekly input directory", { inputDir });
  const files = await fs.readdir(inputDir);
  const reports = await readReports(inputDir, files);
  if (!reports.length) throw new Error(`No weekly health JSON reports found in ${inputDir}`);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.mkdir(previewDir, { recursive: true });

  const deck = buildMonthlySynthesisDeck(reports);
  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlobToFile(path.join(previewDir, `${stem}.png`), await deck.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(previewDir, `${stem}.layout.json`), await layout.text(), "utf8");
  }
  await writeBlobToFile(path.join(previewDir, "monthly-synthesis-montage.webp"), await deck.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(outputPath);
  const manifest = {
    month,
    generatedAt: new Date().toISOString(),
    inputDir,
    outputPath,
    previewDir,
    projectCount: reports.length,
    projects: reports.map((report) => ({
      projectName: report.project_name,
      rag: report.rag,
      score: report.score,
      confidence: report.confidence,
    })),
  };
  await fs.writeFile(path.join(path.dirname(outputPath), "monthly_manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
  await writeLogEntry("info", "Wrote monthly deck", { outputPath, projectCount: reports.length });
}

main().catch((error) => {
  const message = error && error.stack ? error.stack : String(error);
  if (logPath) {
    fs.appendFile(logPath, `${new Date().toISOString()} ERROR monthly_presentation - ${message}\n`, "utf8").catch(() => {});
  }
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
