#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const readline = require("readline");

const ROOT = path.resolve(__dirname, "..");
const PACKAGE_VERSION = require(path.join(ROOT, "package.json")).version;
const SKILL_ROOT = path.join(ROOT, "skills");
const INSTALL_MANIFEST = ".cn-thesis-docx-skills-install.json";
const SKILLS = {
  review: "thesis-literature-review-builder",
  proposal: "thesis-proposal-report-builder"
};
const TOOLS = ["codex", "claude", "opencode", "agents", "all"];
const SCOPES = ["global", "project"];

function usage() {
  console.log(`Usage:
  node bin/install.js install
  node bin/install.js update
  node bin/install.js install --skill review --tool codex --scope global
  node bin/install.js update --skill proposal --scope project --project-dir <path>

Options:
  --skill <review|proposal|all>
  --tool <codex|claude|opencode|agents|all>
  --scope <global|project>
  --project-dir <path>      Project directory for project-scoped installs/updates
  --force                   Replace a modified or legacy installation (a backup is kept)
  --dry-run                 Show changes without updating (update only)
  --check                   Validate package source and print compatibility information
`);
}

function optionValue(rest, index, option) {
  const value = rest[index + 1];
  if (!value || value.startsWith("-")) {
    throw new Error(`${option} requires a value.`);
  }
  return value;
}

function parseArgs(argv) {
  const args = {
    command: "install",
    projectDir: process.cwd(),
    force: false,
    dryRun: false,
    check: false
  };
  const rest = argv.slice(2);
  if (rest[0] && !rest[0].startsWith("-")) args.command = rest.shift();
  for (let i = 0; i < rest.length; i++) {
    const option = rest[i];
    if (option === "--skill") args.skill = optionValue(rest, i++, option);
    else if (option === "--tool") args.tool = optionValue(rest, i++, option);
    else if (option === "--scope") args.scope = optionValue(rest, i++, option);
    else if (option === "--project-dir") args.projectDir = path.resolve(optionValue(rest, i++, option));
    else if (option === "--force") args.force = true;
    else if (option === "--dry-run") args.dryRun = true;
    else if (option === "--check") args.check = true;
    else if (option === "-h" || option === "--help") args.help = true;
    else throw new Error(`Unknown argument: ${option}`);
  }
  return args;
}

function homePath(...parts) {
  return path.join(os.homedir(), ...parts);
}

function opencodeConfigDir() {
  if (process.env.OPENCODE_CONFIG_HOME) return process.env.OPENCODE_CONFIG_HOME;
  if (process.env.XDG_CONFIG_HOME) return path.join(process.env.XDG_CONFIG_HOME, "opencode");
  return homePath(".config", "opencode");
}

function targetFor(tool, scope, projectDir, skillName) {
  if (scope === "project") {
    if (tool === "codex") return path.join(projectDir, ".codex", "skills", skillName);
    if (tool === "claude") return path.join(projectDir, ".claude", "skills", skillName);
    if (tool === "opencode") return path.join(projectDir, ".opencode", "skills", skillName);
    if (tool === "agents") return path.join(projectDir, ".agents", "skills", skillName);
  }
  if (scope === "global") {
    if (tool === "codex") return path.join(process.env.CODEX_HOME || homePath(".codex"), "skills", skillName);
    if (tool === "claude") return homePath(".claude", "skills", skillName);
    if (tool === "opencode") return path.join(opencodeConfigDir(), "skills", skillName);
    if (tool === "agents") return homePath(".agents", "skills", skillName);
  }
  throw new Error(`Unsupported target: tool=${tool}, scope=${scope}`);
}

function sourceEntries(dir, relative = "") {
  const entries = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__pycache__" || entry.name === ".DS_Store") continue;
    const childRelative = relative ? path.join(relative, entry.name) : entry.name;
    const child = path.join(dir, entry.name);
    if (entry.isDirectory()) entries.push(...sourceEntries(child, childRelative));
    else if (entry.isFile()) entries.push(childRelative);
  }
  return entries.sort();
}

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function buildManifest(src, skillName) {
  const files = {};
  for (const relative of sourceEntries(src)) {
    files[relative.replaceAll(path.sep, "/")] = sha256(path.join(src, relative));
  }
  return {
    package: "cn-thesis-docx-skills",
    packageVersion: PACKAGE_VERSION,
    skillName,
    files
  };
}

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      if (entry === "__pycache__" || entry === ".DS_Store") continue;
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
  }
}

function removeRecursive(target) {
  if (fs.existsSync(target)) fs.rmSync(target, { recursive: true, force: true });
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function installationState(dest, skillName) {
  if (!fs.existsSync(dest)) return { state: "missing" };
  if (!fs.existsSync(path.join(dest, "SKILL.md"))) return { state: "not-skill" };
  const manifest = readJson(path.join(dest, INSTALL_MANIFEST));
  if (!manifest || manifest.skillName !== skillName || !manifest.files) {
    return { state: "legacy" };
  }
  const actualFiles = sourceEntries(dest)
    .filter((relative) => relative !== INSTALL_MANIFEST)
    .map((relative) => relative.replaceAll(path.sep, "/"));
  const expectedFiles = Object.keys(manifest.files).sort();
  if (JSON.stringify(actualFiles) !== JSON.stringify(expectedFiles)) return { state: "modified" };
  for (const relative of expectedFiles) {
    if (sha256(path.join(dest, relative)) !== manifest.files[relative]) return { state: "modified" };
  }
  return { state: "managed", manifest };
}

function createStage(src, dest, skillName) {
  const parent = path.dirname(dest);
  fs.mkdirSync(parent, { recursive: true });
  const stage = path.join(parent, `.${path.basename(dest)}.staging-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  copyRecursive(src, stage);
  fs.writeFileSync(path.join(stage, INSTALL_MANIFEST), `${JSON.stringify(buildManifest(src, skillName), null, 2)}\n`, "utf8");
  return stage;
}

function backupPath(dest) {
  return `${dest}.backup-${new Date().toISOString().replace(/[:.]/g, "-")}`;
}

function activateStage(stage, dest) {
  let backup = null;
  if (fs.existsSync(dest)) {
    backup = backupPath(dest);
    fs.renameSync(dest, backup);
  }
  try {
    fs.renameSync(stage, dest);
  } catch (error) {
    if (backup && fs.existsSync(backup) && !fs.existsSync(dest)) fs.renameSync(backup, dest);
    throw error;
  }
  return backup;
}

function rollback(committed) {
  for (const item of committed.reverse()) {
    removeRecursive(item.dest);
    if (item.backup && fs.existsSync(item.backup)) fs.renameSync(item.backup, item.dest);
  }
}

function ask(question, choices) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(`${question} (${choices.join("/")}): `, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

async function resolveChoice(args) {
  let skill = args.skill;
  let tool = args.tool;
  let scope = args.scope;
  const skillChoices = ["review", "proposal", "all"];
  if (!skill) skill = await ask("Install which skill?", skillChoices);
  if (!tool) tool = await ask("Install for which tool?", TOOLS);
  if (!scope) scope = await ask("Install globally or for this project?", SCOPES);
  skill = skill.toLowerCase();
  tool = tool.toLowerCase();
  scope = scope.toLowerCase();
  if (!skillChoices.includes(skill)) throw new Error(`Invalid --skill: ${skill}`);
  if (!TOOLS.includes(tool)) throw new Error(`Invalid --tool: ${tool}`);
  if (!SCOPES.includes(scope)) throw new Error(`Invalid --scope: ${scope}`);
  return { skill, tool, scope };
}

function selectedSkills(skill) {
  return skill === "all" ? Object.values(SKILLS) : [SKILLS[skill]];
}

function selectedTools(tool) {
  return tool === "all" ? TOOLS.filter((item) => item !== "all") : [tool];
}

function validateOptionalFilters(args) {
  const skillChoices = ["review", "proposal", "all"];
  if (args.skill) {
    args.skill = args.skill.toLowerCase();
    if (!skillChoices.includes(args.skill)) throw new Error(`Invalid --skill: ${args.skill}`);
  }
  if (args.tool) {
    args.tool = args.tool.toLowerCase();
    if (!TOOLS.includes(args.tool)) throw new Error(`Invalid --tool: ${args.tool}`);
  }
  if (args.scope) {
    args.scope = args.scope.toLowerCase();
    if (!SCOPES.includes(args.scope)) throw new Error(`Invalid --scope: ${args.scope}`);
  }
}

function sourceFor(skillName) {
  const src = path.join(SKILL_ROOT, skillName);
  if (!fs.existsSync(path.join(src, "SKILL.md"))) throw new Error(`Missing skill source: ${src}`);
  return src;
}

function installPlans(skill, tool, scope, projectDir, force) {
  const plans = [];
  for (const skillName of selectedSkills(skill)) {
    const src = sourceFor(skillName);
    for (const targetTool of selectedTools(tool)) {
      const dest = targetFor(targetTool, scope, projectDir, skillName);
      const existing = installationState(dest, skillName);
      if (existing.state !== "missing" && !force) {
        throw new Error(`${dest} already exists. Re-run with --force to replace it; a backup will be kept.`);
      }
      if (existing.state === "not-skill") {
        throw new Error(`Refusing to replace a non-skill directory: ${dest}`);
      }
      plans.push({ src, dest, skillName, action: existing.state === "missing" ? "install" : "replace" });
    }
  }
  return plans;
}

function updatePlans(args) {
  validateOptionalFilters(args);
  const plans = [];
  for (const skillName of selectedSkills(args.skill || "all")) {
    const src = sourceFor(skillName);
    for (const tool of selectedTools(args.tool || "all")) {
      for (const scope of args.scope ? [args.scope] : SCOPES) {
        const dest = targetFor(tool, scope, args.projectDir, skillName);
        const existing = installationState(dest, skillName);
        if (existing.state === "missing") continue;
        if (existing.state === "not-skill") throw new Error(`Refusing to overwrite a non-skill directory: ${dest}`);
        if ((existing.state === "modified" || existing.state === "legacy") && !args.force) {
          throw new Error(`${dest} is ${existing.state === "legacy" ? "not managed by this installer" : "locally modified"}. Re-run with --force to replace it; a backup will be kept.`);
        }
        plans.push({ src, dest, skillName, action: "update", state: existing.state });
      }
    }
  }
  return plans;
}

function applyPlans(plans) {
  const staged = [];
  try {
    for (const plan of plans) staged.push({ ...plan, stage: createStage(plan.src, plan.dest, plan.skillName) });
  } catch (error) {
    for (const plan of staged) removeRecursive(plan.stage);
    throw error;
  }
  const committed = [];
  try {
    for (const plan of staged) committed.push({ ...plan, backup: activateStage(plan.stage, plan.dest) });
  } catch (error) {
    rollback(committed);
    for (const plan of staged) removeRecursive(plan.stage);
    throw error;
  }
  return committed;
}

function printPlans(plans, heading) {
  console.log(heading);
  for (const plan of plans) console.log(`  - ${plan.action}: ${plan.dest}`);
}

function printNoMatch(args) {
  console.log("No installed skills matched the selected filters.");
  console.log("Use the install command first, or adjust --skill/--tool/--scope filters.");
  if (args.command === "update") {
    console.log(`Project directory scanned for --scope project: ${args.projectDir}`);
    console.log("If the skill was installed into another project, run:");
    console.log("  node bin/install.js update --project-dir <path-to-that-project>");
    if (path.resolve(args.projectDir) === ROOT) {
      console.log("You are running from the cn-thesis-docx-skills source repo; project-scoped installs usually live in your thesis/project folder, not here.");
    }
  }
}

function printCheck(projectDir) {
  const major = Number(process.versions.node.split(".")[0]);
  if (major < 18) throw new Error(`Node.js 18+ is required; found ${process.version}.`);
  console.log(`Package source: ${ROOT}`);
  console.log(`Package version: ${PACKAGE_VERSION}`);
  console.log(`Node: ${process.version}`);
  console.log(`Platform: ${process.platform} ${process.arch}`);
  console.log("Available skills:");
  for (const [key, skillName] of Object.entries(SKILLS)) {
    sourceFor(skillName);
    console.log(`  ${key}: ${skillName}`);
  }
  console.log("Python scripts require Python 3.10+; citation conversion and report audit require lxml.");
  console.log(`Project root used for --scope project: ${projectDir}`);
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) return usage();
  if (args.command !== "install" && args.command !== "update" && !args.check) {
    throw new Error(`Unsupported command: ${args.command}`);
  }
  if (args.check) return printCheck(args.projectDir);
  if (args.dryRun && args.command !== "update") throw new Error("--dry-run is only supported by the update command.");

  const plans = args.command === "update"
    ? updatePlans(args)
    : installPlans(...Object.values(await resolveChoice(args)), args.projectDir, args.force);
  if (plans.length === 0) {
    printNoMatch(args);
    return;
  }
  if (args.dryRun) return printPlans(plans, "Skills that would be updated:");
  const committed = applyPlans(plans);
  printPlans(committed, args.command === "update" ? "Updated skills:" : "Installed skills:");
  const backups = committed.filter((item) => item.backup);
  if (backups.length) {
    console.log("Backups kept for recovery:");
    for (const item of backups) console.log(`  - ${item.backup}`);
  }
  console.log("Restart or reload the target agent if it does not detect the new skill automatically.");
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exit(1);
});
