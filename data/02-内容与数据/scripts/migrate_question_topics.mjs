import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DATA = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'data');
const FILE = resolve(DATA, 'question_bank.csv');
const SNAPSHOT = resolve(DATA, '历史快照', '2026-07-31-正式专题迁移前');
const apply = process.argv.includes('--apply');
const TOPIC_MAP = new Map([
  ['rl-001', 'ml-course-001'],
  ['dl-base-001', 'dl-course-001'],
  ['ml-core-001', 'ml-course-001'],
  ['dl-core-001', 'dl-course-001'],
]);

function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted && char === '"' && text[index + 1] === '"') { cell += '"'; index += 1; continue; }
    if (char === '"') { quoted = !quoted; continue; }
    if (!quoted && char === ',') { row.push(cell); cell = ''; continue; }
    if (!quoted && (char === '\n' || char === '\r')) { if (char === '\r' && text[index + 1] === '\n') index += 1; row.push(cell); cell = ''; if (row.some(value => value !== '')) rows.push(row); row = []; continue; }
    cell += char;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [headers, ...values] = rows;
  return { headers, rows: values.map(valueRow => Object.fromEntries(headers.map((header, index) => [header, valueRow[index] ?? '']))) };
}
const escape = value => { const text = String(value ?? ''); return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text; };
const stringify = ({ headers, rows }) => `${headers.join(',')}\n${rows.map(row => headers.map(header => escape(row[header])).join(',')).join('\n')}\n`;

const source = parseCsv(await readFile(FILE, 'utf8'));
if (source.headers.includes('legacy_topic_id')) throw new Error('题库已经完成正式专题迁移，停止以避免重复写入。');
const migratedRows = source.rows.map(row => {
  const nextTopic = TOPIC_MAP.get(row.topic_id) ?? row.topic_id;
  return { ...row, topic_id: nextTopic, legacy_topic_id: nextTopic === row.topic_id ? '' : row.topic_id };
});
const changed = migratedRows.filter((row, index) => row.legacy_topic_id).length;
const output = { headers: [...source.headers, 'legacy_topic_id'], rows: migratedRows };
console.log(`预览：${changed} 道题将迁移到当前正式专题；旧专题 ID 将写入 legacy_topic_id。`);
if (apply) {
  await mkdir(SNAPSHOT, { recursive: true });
  await writeFile(resolve(SNAPSHOT, 'question_bank.csv'), stringify(source), 'utf8');
  await writeFile(FILE, stringify(output), 'utf8');
  console.log(`已写入；迁移前快照保存在 ${SNAPSHOT}`);
}
