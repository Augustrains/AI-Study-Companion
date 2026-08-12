/**
 * 将已下载的开放教材源文件转换为“待审核”的可读 Markdown。
 * 不生成题目，也不会自动把内容标记为 approved。
 */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CONTENT_ROOT = resolve(HERE, '..');
const DATA_DIR = join(CONTENT_ROOT, 'data');
const RAW_DIR = join(CONTENT_ROOT, '原始资料');
const OUTPUT_DIR = join(CONTENT_ROOT, '资料库', '待审核');

function csvRows(text) {
  const lines = text.trim().split(/\r?\n/);
  const parse = line => {
    const cells = []; let cell = ''; let quoted = false;
    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      if (char === '"' && quoted && line[index + 1] === '"') { cell += '"'; index += 1; }
      else if (char === '"') quoted = !quoted;
      else if (char === ',' && !quoted) { cells.push(cell); cell = ''; }
      else cell += char;
    }
    cells.push(cell); return cells;
  };
  const headers = parse(lines.shift());
  return lines.filter(Boolean).map(line => Object.fromEntries(headers.map((header, index) => [header, parse(line)[index] ?? ''])));
}

async function readCsv(name) { return csvRows(await readFile(join(DATA_DIR, name), 'utf8')); }
function cleanMarkdown(text) {
  return text.replace(/\r/g, '')
    .replace(/^---[\s\S]*?---\s*/m, '')
    // Jupyter Book / MyST 的图片、视频、目录、引用和脚本容器无法在本地阅读页稳定呈现，抽取时整体移除；正文和代码块保留给人工审核。
    .replace(/^(?:>\s*)?:::\{[^}]+\}[\s\S]*?^(?:>\s*)?:::\s*$/gm, '')
    .replace(/^:::\{[^}]+\}\s*$/gm, '')
    .replace(/^\s*:\w[\w-]*:.*$/gm, '')
    .replace(/^#@tab\s+.*$/gm, '')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/^\s*<\/?(?:div|span|p)[^>]*>\s*$/gim, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
function notebookToMarkdown(raw) {
  const notebook = JSON.parse(raw);
  return (notebook.cells ?? []).map(cell => {
    const source = Array.isArray(cell.source) ? cell.source.join('') : String(cell.source ?? '');
    if (!source.trim()) return '';
    if (cell.cell_type === 'markdown') return source;
    if (cell.cell_type === 'code') return `\n\`\`\`python\n${source.trim()}\n\`\`\`\n`;
    return '';
  }).join('\n\n');
}

const [sources, units, edges] = await Promise.all([
  readCsv('source_catalog.csv'), readCsv('content_unit_catalog.csv'), readCsv('content_unit_knowledge_edges.csv')
]);
let generated = 0; let skipped = 0;
for (const unit of units) {
  const source = sources.find(row => row.source_id === unit.source_id);
  const input = resolve(RAW_DIR, source.local_directory, unit.source_relative_path);
  const sourceRoot = resolve(RAW_DIR, source.local_directory);
  if (!input.startsWith(sourceRoot) || !existsSync(input)) { skipped += 1; continue; }
  const raw = await readFile(input, 'utf8');
  const body = cleanMarkdown(extname(input) === '.ipynb' ? notebookToMarkdown(raw) : raw);
  const knowledgePointIds = edges.filter(edge => edge.content_unit_id === unit.content_unit_id).map(edge => edge.knowledge_point_id).join(', ');
  const output = join(OUTPUT_DIR, unit.book_id, `${unit.content_unit_id}.md`);
  await mkdir(dirname(output), { recursive: true });
  const frontMatter = [
    '---',
    `content_unit_id: ${unit.content_unit_id}`,
    `book_id: ${unit.book_id}`,
    `topic_id: ${unit.topic_id}`,
    `chapter: ${unit.chapter_name}`,
    `knowledge_points: [${knowledgePointIds}]`,
    `source_id: ${source.source_id}`,
    `source_relative_path: ${unit.source_relative_path}`,
    `source_commit: ${unit.source_commit}`,
    `license: ${source.license}`,
    `source_url: ${unit.source_url}`,
    `attribution: ${source.source_title} — ${source.authors}`,
    `cleaning_status: draft`,
    `review_status: pending`,
    '---',
    '',
    `# ${unit.chapter_name}：${unit.section_title}`,
    '',
    `> 来源：${source.source_title}；许可证：${source.license}；固定版本：${unit.source_commit}。`,
    '',
    body,
    ''
  ].join('\n');
  await writeFile(output, frontMatter, 'utf8');
  generated += 1;
}
console.log(`已生成 ${generated} 个待审核内容单元；跳过 ${skipped} 个缺少本地源文件的单元。`);
