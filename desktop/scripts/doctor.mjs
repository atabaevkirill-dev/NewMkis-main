import { spawnSync } from "node:child_process";

const problems = [];
const [major, minor] = process.versions.node.split(".").map(Number);

console.log(`Node.js: ${process.version}`);
if (major < 22 || (major === 22 && minor < 12)) {
  problems.push("Нужен Node.js 22.12 или новее (рекомендуется Node 22 LTS).");
}

for (const command of ["npm", "rustc", "cargo"]) {
  const result = spawnSync(command, ["--version"], { encoding: "utf8", shell: process.platform === "win32" });
  if (result.error || result.status !== 0) {
    problems.push(`Не найден ${command}.`);
  } else {
    console.log(`${command}: ${result.stdout.trim()}`);
  }
}

console.log(`Platform: ${process.platform} ${process.arch}`);

if (problems.length) {
  console.error("\nОкружение не готово:");
  for (const problem of problems) console.error(`- ${problem}`);
  process.exit(1);
}

console.log("\nОкружение готово к сборке ONCAM Cockpit.");
