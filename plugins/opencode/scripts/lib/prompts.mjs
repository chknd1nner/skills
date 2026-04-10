import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE_DIR = path.resolve(__dirname, "../../prompts");

const WORKING_TREE_SECTION = `**Scope:** All uncommitted changes — staged, unstaged, and untracked files.

To enumerate the changes, run from \`{{WORKSPACE}}\`:
- \`git status --short --untracked-files=all\`
- \`git diff --cached\`  (staged changes)
- \`git diff\`           (unstaged changes)
- For untracked files, read each one directly with your Read tool.`;

const BRANCH_SECTION = `**Scope:** Commits between \`{{BASE_REF}}\` and \`HEAD\`.

To enumerate the changes, run from \`{{WORKSPACE}}\`:
- \`git log --oneline {{BASE_REF}}..HEAD\`
- \`git diff {{BASE_REF}}...HEAD --stat\`
- \`git diff {{BASE_REF}}...HEAD\`  (full diff if you need it; use --name-only first to scope)`;

/**
 * Build the review prompt by interpolating the template.
 * @param {{ mode: string, baseRef?: string, label: string }} target
 * @param {string} cwd
 * @returns {string}
 */
export function buildReviewPrompt(target, cwd) {
  let template = fs.readFileSync(
    path.join(TEMPLATE_DIR, "review.md"),
    "utf8"
  );

  // Conditional sections
  if (target.mode === "working-tree") {
    template = template.replace(
      "{{WORKING_TREE_SECTION}}",
      WORKING_TREE_SECTION
    );
    template = template.replace("{{BRANCH_SECTION}}", "");
  } else {
    template = template.replace("{{WORKING_TREE_SECTION}}", "");
    template = template.replace("{{BRANCH_SECTION}}", BRANCH_SECTION);
  }

  // Simple variable interpolation
  template = template.replaceAll("{{WORKSPACE}}", cwd);
  template = template.replaceAll("{{TARGET_MODE}}", target.mode);
  template = template.replaceAll("{{TARGET_LABEL}}", target.label);
  if (target.baseRef) {
    template = template.replaceAll("{{BASE_REF}}", target.baseRef);
  }

  // Clean up any remaining empty lines from removed sections
  template = template.replace(/\n{3,}/g, "\n\n");

  return template;
}
