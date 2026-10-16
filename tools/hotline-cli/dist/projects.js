import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { parse } from "yaml";
export const rootDir = resolve(import.meta.dirname, "../../..");
export const projectsDir = join(rootDir, "projects");
export function discoverProjects(errors = []) {
    if (!existsSync(projectsDir))
        return [];
    const result = [];
    for (const category of readdirSync(projectsDir, { withFileTypes: true })) {
        if (!category.isDirectory())
            continue;
        const categoryPath = join(projectsDir, category.name);
        for (const entry of readdirSync(categoryPath, { withFileTypes: true })) {
            if (!entry.isDirectory())
                continue;
            const projectDir = join(categoryPath, entry.name);
            const metadataPath = join(projectDir, "project.yaml");
            if (!existsSync(metadataPath))
                continue;
            let metadata;
            try {
                metadata = parse(readFileSync(metadataPath, "utf8"));
                if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata))
                    throw new Error('清单必须是对象');
            }
            catch (error) {
                errors.push(`${relative(rootDir, projectDir).replaceAll("\\", "/")}: project.yaml 解析失败：${error instanceof Error ? error.message : "未知错误"}`);
                continue;
            }
            const commands = metadata.commands;
            if (metadata.hidden === true)
                continue;
            const runCommand = commands?.start ?? commands?.run;
            const validCommand = typeof runCommand === 'string' ? runCommand.trim().length > 0
                : Array.isArray(runCommand) && runCommand.length > 0 && runCommand.every(v => typeof v === 'string') && runCommand[0].trim().length > 0;
            result.push({
                path: relative(rootDir, projectDir).replaceAll("\\", "/"),
                name: String(metadata.name ?? entry.name),
                category: String(metadata.category ?? category.name),
                status: metadata.status ? String(metadata.status) : undefined,
                description: metadata.description ? String(metadata.description) : undefined,
                language: Array.isArray(metadata.language) ? metadata.language.map(String) : undefined,
                mode: metadata.mode ? String(metadata.mode) : undefined,
                url: typeof metadata.url === 'string' && metadata.url.trim() ? metadata.url.trim() : undefined,
                healthChecks: Array.isArray(metadata.healthChecks) ? metadata.healthChecks.filter((v) => typeof v === 'string') : undefined,
                runCommand: validCommand
                    ? runCommand
                    : undefined
            });
        }
    }
    return result.sort((a, b) => a.path.localeCompare(b.path));
}
