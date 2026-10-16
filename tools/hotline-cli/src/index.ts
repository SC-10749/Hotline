import { existsSync } from "node:fs";
import { join } from "node:path";
import { discoverProjects, rootDir } from "./projects.js";

function usage(): void {
  console.log("用法: npm run hotline（启动基础平台）\n      pnpm hotline <dashboard|list|search|info|validate> [关键词或项目路径]");
}

const [command, argument] = process.argv.slice(2);
const projects = discoverProjects();

if (!command || command === "dashboard") {
  await import("./dashboard.js");
} else if (command === "help" || command === "--help" || command === "-h") {
  usage();
} else if (command === "list") {
  if (projects.length === 0) console.log("当前没有包含 project.yaml 的项目。");
  for (const project of projects) {
    console.log(`${project.path}  [${project.status ?? "unknown"}]  ${project.description ?? ""}`);
  }
} else if (command === "search") {
  const query = (argument ?? "").toLowerCase();
  for (const project of projects.filter((item) =>
    JSON.stringify(item).toLowerCase().includes(query)
  )) {
    console.log(`${project.path}  [${project.status ?? "unknown"}]  ${project.description ?? ""}`);
  }
} else if (command === "info") {
  const project = projects.find((item) => item.path === argument || item.name === argument);
  if (!project) {
    console.error(`找不到项目: ${argument ?? ""}`);
    process.exitCode = 1;
  } else {
    console.log(JSON.stringify(project, null, 2));
  }
} else if (command === "validate") {
  const errors: string[] = [];
  for (const project of projects) {
    if (!project.description) errors.push(`${project.path}: 缺少 description`);
    if (!project.status) errors.push(`${project.path}: 缺少 status`);
    if (!project.mode) errors.push(`${project.path}: 缺少 mode`);
    if (!existsSync(join(rootDir, project.path, "README.md"))) {
      errors.push(`${project.path}: 缺少 README.md`);
    }
  }
  if (errors.length > 0) {
    console.error(errors.join("\n"));
    process.exitCode = 1;
  } else {
    console.log(`验证通过：${projects.length} 个项目。`);
  }
} else {
  usage();
  process.exitCode = 1;
}

