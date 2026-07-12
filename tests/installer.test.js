"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const cli = path.join(root, "bin", "install.js");

function run(args) {
  return spawnSync(process.execPath, [cli, ...args], { encoding: "utf8" });
}

test("installer protects local modifications and keeps a backup on forced update", () => {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "cn-thesis-docx-skills-"));
  try {
    const install = run(["install", "--skill", "review", "--tool", "codex", "--scope", "project", "--project-dir", project]);
    assert.strictEqual(install.status, 0, install.stderr);
    const dest = path.join(project, ".codex", "skills", "thesis-literature-review-builder");
    assert.ok(fs.existsSync(path.join(dest, ".cn-thesis-docx-skills-install.json")));

    fs.writeFileSync(path.join(dest, "local-note.txt"), "user customization\n", "utf8");
    const protectedUpdate = run(["update", "--skill", "review", "--tool", "codex", "--scope", "project", "--project-dir", project]);
    assert.notStrictEqual(protectedUpdate.status, 0);
    assert.match(protectedUpdate.stderr, /locally modified/);
    assert.ok(fs.existsSync(path.join(dest, "local-note.txt")));

    const forcedUpdate = run(["update", "--skill", "review", "--tool", "codex", "--scope", "project", "--project-dir", project, "--force"]);
    assert.strictEqual(forcedUpdate.status, 0, forcedUpdate.stderr);
    assert.ok(!fs.existsSync(path.join(dest, "local-note.txt")));
    const backups = fs.readdirSync(path.dirname(dest)).filter((name) => name.startsWith("thesis-literature-review-builder.backup-"));
    assert.strictEqual(backups.length, 1);
    assert.ok(fs.existsSync(path.join(path.dirname(dest), backups[0], "local-note.txt")));
  } finally {
    fs.rmSync(project, { recursive: true, force: true });
  }
});

test("installer reports missing option values clearly", () => {
  const result = run(["install", "--project-dir"]);
  assert.notStrictEqual(result.status, 0);
  assert.match(result.stderr, /--project-dir requires a value/);
});

test("project update with no matches explains --project-dir", () => {
  const result = run(["update", "--skill", "review", "--tool", "codex", "--scope", "project"]);
  assert.strictEqual(result.status, 0, result.stderr);
  assert.match(result.stdout, /No installed skills matched/);
  assert.match(result.stdout, /node bin\/install\.js update --project-dir <path-to-that-project>/);
  assert.match(result.stdout, /source repo/);
});
