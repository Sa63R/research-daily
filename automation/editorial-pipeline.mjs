import { compactMessages, editorialChunks, validateTimelineEvidenceTimes } from './model-input.mjs';
import { validateEditorialReport } from './editorial.mjs';

const roles = ['highlights', 'timeline', 'uncertain'];
export function emptyEditorialReport() {
  return { schemaVersion: 2, title: '', summary: '', highlights: [], timeline: [], uncertain: [] };
}

async function parallelMap(values, fn, concurrency = 2) {
  const results = new Array(values.length);
  let next = 0;
  const workers = await Promise.allSettled(Array.from({ length: Math.min(concurrency, values.length) }, async () => {
    while (next < values.length) {
      const index = next++;
      results[index] = await fn(values[index], index);
    }
  }));
  const failure = workers.find(result => result.status === 'rejected');
  if (failure) throw failure.reason;
  return results;
}

function contextFor(messages, reports, role) {
  const ids = new Set(reports.flatMap(report => report[role].flatMap(item => item.evidenceIds)));
  const indices = new Set();
  messages.forEach((message, index) => {
    if (!ids.has(message.id)) return;
    for (let i = Math.max(0, index - 2); i <= Math.min(messages.length - 1, index + 2); i++) indices.add(i);
  });
  return compactMessages([...indices].sort((a, b) => a - b).map(index => messages[index]));
}

// Every stage receives its own purpose and evidence boundary. The caller owns
// model execution, caching and retries; this module never collects or publishes.
export async function generateEditorialReport(packet, { summarize, onProgress = () => {}, chunkOptions = {} } = {}) {
  const messages = [...packet.messages].sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
  const chunks = editorialChunks(compactMessages(messages), chunkOptions);
  if (!chunks.length) return {
    ...emptyEditorialReport(), title: '暂无可整理文字',
    summary: '已返回的消息中没有可供整理的文字内容。',
  };
  let completed = 0;
  onProgress({ stage: '正在分批提取重点、讨论与疑问', batches: chunks.length, completedBatches: completed });
  const extracted = await parallelMap(chunks, async (chunk, index) => {
    const chunkIds = new Set(chunk.map(message => message.id));
    const options = { packet: { ...packet, messages: messages.filter(message => chunkIds.has(message.id)) }, extract: true };
    const report = await summarize({ stage: 'extract', date: packet.date, coverage: packet.coverage, messages: chunk }, `v2-part-${index + 1}`, options);
    validateEditorialReport(report, options.packet, { extract: true });
    validateTimelineEvidenceTimes(report, options.packet);
    onProgress({ stage: '正在分批提取重点、讨论与疑问', batches: chunks.length, completedBatches: ++completed });
    return report;
  });

  onProgress({ stage: '正在分别编辑重点、讨论脉络与待核实信息', batches: chunks.length });
  const edited = await parallelMap(roles, async role => {
    const candidates = extracted.map(report => ({
      ...emptyEditorialReport(), title: report.title, summary: '', [role]: report[role],
    }));
    if (!candidates.some(report => report[role].length)) return [];
    const report = await summarize({
      stage: 'edit', section: role, date: packet.date, coverage: packet.coverage, candidates,
      evidenceMessages: contextFor(messages, extracted, role),
      otherRoleTitles: Object.fromEntries(roles.filter(other => other !== role).map(other => [other, extracted.flatMap(report => report[other].map(item => item.title))])),
      crossRoleReview: {
        purpose: '其他栏目的候选仅用于发现较晚的纠正、矛盾和重复：可以删减或降低本栏表述的确定性，不能借用其证据新增或升级本栏结论。',
        candidates: Object.fromEntries(roles.filter(other => other !== role).map(other => [other, extracted.flatMap(report => report[other])])),
      },
    }, `v2-${role}`, { packet, candidates, section: role, final: true });
    validateEditorialReport(report, packet, { candidates, section: role, final: true });
    validateTimelineEvidenceTimes(report, packet);
    return report[role];
  });
  const report = { ...emptyEditorialReport(), title: '保研与科研日报', summary: '', ...Object.fromEntries(roles.map((role, index) => [role, edited[index]])) };
  validateEditorialReport(report, packet, { candidates: extracted, final: true });
  if (roles.some(role => report[role].length)) {
    onProgress({ stage: '正在编写导读并检查日报结构' });
    const overview = await summarize({ stage: 'overview', date: packet.date, report }, 'v2-overview', { packet, section: 'overview' });
    validateEditorialReport(overview, packet, { section: 'overview' });
    report.title = overview.title;
    report.summary = overview.summary;
  } else {
    report.summary = '今天已读取的消息中，没有筛选到符合主题的新信息。';
  }
  return validateEditorialReport(report, packet, { candidates: extracted, final: true });
}
