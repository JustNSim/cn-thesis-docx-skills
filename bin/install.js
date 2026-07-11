#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const os = require("os");
const readline = require("readline");

const ROOT = path.resolve(__dirname, "..");
const SKILL_ROOT = path.join(ROOT, "skills");
const SKILLS = {
  review: "thesis-literature-review-builder",
  proposal: "thesis-proposal-report-builder"
};
const TOOLS = ["codex", "claude", "opencode", "agents", "all"];
const SCOPES = ["global", "project"];

function usage() {
  console.log(`Usage:
  npx cn-thesis-docx-skills install
  npx cn-thesis-docx-skills@latest update
  cn-thesis-docx-skills install --skill review --tool codex --scope global
  cn-thesis-docx-skills install --skill proposal --tool claude --scope project
  cn-thesis-docx-skills install --skill all --tool opencode --scope global
  cn-thesis-docx-skills update --skill review --scope project

Options:
  --skill <review|proposal|all>
  --tool <codex|claude|opencode|agents|all>
  --scope <global|project>
  --project-dir <path>      Defaults to current working directory
  --force                   Overwrite an existing installed skill
  --dry-run                 Show installed skills that would be updated (update only)
  --check                   Print compatibility information only
`);
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
    const a = rest[i];
    if (a === "--skill") args.skill = rest[++i];
    else if (a === "--tool") args.tool = rest[++i];
    else if (a === "--scope") args.scope = rest[++i];
    else if (a === "--project-dir") args.projectDir = path.resolve(rest[++i]);
    else if (a === "--force") args.force = true;
    else if (a === "--dry-run") args.dryRun = true;
    else if (a === "--check") args.check = true;
    else if (a === "-h" || a === "--help") args.help = true;
    else throw new Error(`Unknown argument: ${a}`);
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

function installOne(tool, scope, projectDir, skillName, force) {
  const src = path.join(SKILL_ROOT, skillName);
  if (!fs.existsSync(path.join(src, "SKILL.md"))) {
    throw new Error(`Missing skill source: ${src}`);
  }
  const dest = targetFor(tool, scope, projectDir, skillName);
  if (fs.existsSync(dest) && !force) {
    throw new Error(`${dest} already exists. Re-run with --force to overwrite.`);
  }
  removeRecursive(dest);
  copyRecursive(src, dest);
  return dest;
}

function updateOne(tool, scope, projectDir, skillName, dryRun) {
  const src = path.join(SKILL_ROOT, skillName);
  const dest = targetFor(tool, scope, projectDir, skillName);
  if (!fs.existsSync(dest)) return null;
  if (!fs.existsSync(path.join(dest, "SKILL.md"))) {
    throw new Error(`Refusing to overwrite a non-skill directory: ${dest}`);
  }
  if (!dryRun) {
    removeRecursive(dest);
    copyRecursive(src, dest);
  }
  return dest;
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
  if (skill === "all") return Object.values(SKILLS);
  return [SKILLS[skill]];
}

function selectedTools(tool) {
  return tool === "all" ? TOOLS.filter((t) => t !== "all") : [tool];
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

function updateInstalled(args) {
  validateOptionalFilters(args);
  const skills = selectedSkills(args.skill || "all");
  const tools = selectedTools(args.tool || "all");
  const scopes = args.scope ? [args.scope] : SCOPES;
  const updated = [];
  for (const skillName of skills) {
    for (const tool of tools) {
      for (const scope of scopes) {
        const dest = updateOne(tool, scope, args.projectDir, skillName, args.dryRun);
        if (dest) updated.push(dest);
      }
    }
  }
  if (updated.length === 0) {
    console.log("No installed skills matched the selected filters.");
    console.log("Use the install command first, or set --project-dir to the project containing the skills.");
    return;
  }
  console.log(args.dryRun ? "Skills that would be updated:" : "Updated skills:");
  for (const dest of updated) console.log(`  - ${dest}`);
  if (!args.dryRun) {
    console.log("Restart or reload the target agent if it does not detect the updated skill automatically.");
  }
}

function printCheck(projectDir) {
  console.log(`Package source: ${ROOT}`);
  console.log(`Node: ${process.version}`);
  console.log(`Platform: ${process.platform} ${process.arch}`);
  console.log("Available skills:");
  for (const [key, skillName] of Object.entries(SKILLS)) {
    console.log(`  ${key}: ${skillName}`);
  }
  for (const skillName of Object.values(SKILLS)) {
    for (const tool of TOOLS.filter((t) => t !== "all")) {
      for (const scope of SCOPES) {
        console.log(`${skillName} -> ${tool}/${scope}: ${targetFor(tool, scope, projectDir, skillName)}`);
      }
    }
  }
  console.log("Python scripts require Python 3.10+; convert_refs_to_crossrefs.py and audit_docx_report.py require lxml.");
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    usage();
    return;
  }
  if (args.command !== "install" && args.command !== "update" && !args.check) {
    throw new Error(`Unsupported command: ${args.command}`);
  }
  if (args.check) {
    printCheck(args.projectDir);
    return;
  }
  if (args.command === "update") {
    updateInstalled(args);
    return;
  }
  if (args.dryRun) {
    throw new Error("--dry-run is only supported by the update command.");
  }
  const { skill, tool, scope } = await resolveChoice(args);
  const installed = [];
  for (const skillName of selectedSkills(skill)) {
    for (const targetTool of selectedTools(tool)) {
      installed.push(installOne(targetTool, scope, args.projectDir, skillName, args.force));
    }
  }
  console.log("Installed skills:");
  for (const dest of installed) console.log(`  - ${dest}`);
  console.log("Restart or reload the target agent if it does not detect the new skill automatically.");
}

main().catch((err) => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});
