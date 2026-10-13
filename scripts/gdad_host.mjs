// Runs a pi-extensible-workflows script with shell + checkpoint bridges.
// pi 0.87.1 cannot host agent(), and a pi model inlines its own script, so this
// process is the orchestrator. Completed shell calls are replayed from
// GDAD_REPLAY, which is how a killed pane resumes without rerunning workers.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { runWorkflow } from "/home/sab-mini/.pi/agent/npm/node_modules/pi-extensible-workflows/dist/src/index.js";

const scriptPath = process.env.GDAD_SCRIPT;
const replayPath = process.env.GDAD_REPLAY;
const releasePath = process.env.GDAD_RELEASE;
if (!scriptPath || !replayPath || !releasePath) {
  console.error("GDAD_SCRIPT, GDAD_REPLAY, and GDAD_RELEASE are required");
  process.exit(2);
}

const done = new Map();
if (fs.existsSync(replayPath)) {
  for (const line of fs.readFileSync(replayPath, "utf8").split("\n")) {
    if (!line.trim()) continue;
    const rec = JSON.parse(line);
    done.set(rec.key, rec.result);
  }
}

function replayKey(command, identity) {
  return JSON.stringify({
    command,
    callSite: identity && identity.callSite,
    occurrence: identity && identity.occurrence,
    structuralPath: identity && identity.structuralPath,
  });
}

function runShell(command) {
  return new Promise((resolve) => {
    const child = spawn(command, { shell: true, env: process.env });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("close", (code) => {
      resolve({ exitCode: code, stdout, stderr });
    });
  });
}

const bridge = {
  async shell(command, _options, _signal, identity) {
    const key = replayKey(command, identity);
    if (done.has(key)) {
      console.log(`replay ${String(identity && identity.occurrence)} ${command.slice(0, 80)}`);
      return done.get(key);
    }
    console.log(`shell ${command.slice(0, 120)}`);
    const result = await runShell(command);
    if (result.exitCode) {
      console.error(result.stderr.slice(0, 800));
      throw new Error(`shell exited ${result.exitCode}`);
    }
    fs.appendFileSync(replayPath, JSON.stringify({ key, result }) + "\n");
    done.set(key, result);
    return result;
  },
  async checkpoint(input) {
    const name = typeof input.name === "string" ? input.name : "checkpoint";
    console.log(`checkpoint ${name}`);
    for (;;) {
      if (fs.existsSync(releasePath) && fs.readFileSync(releasePath, "utf8").includes(name)) {
        console.log(`released ${name}`);
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  },
};

const script = fs.readFileSync(scriptPath, "utf8");
try {
  const value = await runWorkflow(script, null, bridge).result;
  console.log("workflow finished");
  console.log(JSON.stringify(value));
} catch (error) {
  console.error(error && error.message ? error.message : error);
  process.exit(1);
}
