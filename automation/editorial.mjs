import { publicText, publicResourceUrl } from './core.mjs';

// Editorial roles, limits and time coverage follow jielosc/csbaoyan-chat-daily
// report_generation.py / report_schema.py (MIT); research resources are added.

const roles = ['highlights', 'timeline', 'uncertain'];
const categories = ['院校与项目', '申请与考核', '经验与选择', '科研与学习'];
const kinds = ['动态', '经验', '分析', '资源'];
const statuses = ['已有答复', '形成共识', '仍有分歧', '没有结论'];
const limits = { highlights: 12, timeline: 24, uncertain: 8 };

function requireText(value, name, { empty = false } = {}) {
  if (typeof value !== 'string' || (!empty && !value.trim())) throw Error(`${name}无效`);
}

function minute(value) {
  if (typeof value !== 'string' || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) throw Error('讨论时间必须使用有效的 HH:mm');
  const [hour, minutes] = value.split(':').map(Number);
  return hour * 60 + minutes;
}

function periods(items) {
  const covered = new Set();
  for (const item of items) {
    const start = minute(item.startTime), end = Math.max(start + 1, minute(item.endTime));
    for (const [index, [lower, upper]] of [[0, 540], [540, 720], [720, 1080], [1080, 1440]].entries()) {
      if (start < upper && end > lower) covered.add(index);
    }
  }
  return covered;
}

function candidateItems(candidates, role) {
  const reports = Array.isArray(candidates) ? candidates : [candidates];
  return reports.flatMap(report => {
    if (!report || report[role] == null) return [];
    if (!Array.isArray(report[role])) throw Error('候选日报结构无效');
    return report[role];
  });
}

function cleanLinks(links, markers) {
  if (!Array.isArray(links)) throw Error('资源链接无效');
  for (const link of links) {
    if (!link || typeof link !== 'object') throw Error('资源链接无效');
    requireText(link.title, '资源链接名称');
    requireText(link.url, '资源链接地址');
    link.url = publicResourceUrl(link.url, markers);
    link.title = publicText(link.title, markers);
  }
}

function questionOnly(value) {
  if (typeof value !== 'string') return false;
  const text = value.replace(/^(?:@群成员\s*)+/, '').trim();
  if (!text || /^https?:\/\/\S+$/.test(text)) return false;
  // A question may contain a useful statement as well. Only downgrade clearly
  // interrogative messages, rather than matching words such as “如何” anywhere.
  if (/[。！!\n].*\S/.test(text.replace(/[？?。！!\s]+$/, ''))) return false;
  return /[？?]$/.test(text) || /(?:吗|么|嘛|呢)[啊呀呐嘛]*[？?。！!…~～\s]*$/.test(text)
    || /^(?:请问|想问|求问|问一下|有人知道|有无懂|有懂|谁知道)/.test(text);
}

/** Validate evidence before removing private information from every public field. */
export function validateEditorialReport(report, packet, { candidates, section, final = false, extract = false } = {}) {
  if (!report || report.schemaVersion !== 2 || !packet || !Array.isArray(packet.messages) || !Array.isArray(packet.coverage)) throw Error('新版日报结构无效');
  requireText(report.title, '日报标题');
  requireText(report.summary, '日报摘要', { empty: true });
  if (section != null && ![...roles, 'overview'].includes(section)) throw Error('编辑栏目无效');
  const known = new Set(packet.messages.map(message => message.id));
  const markers = [...known, ...new Set(packet.messages.map(message => message.author).filter(Boolean)), ...packet.coverage.map(coverage => coverage.group).filter(Boolean)];

  if (extract && Array.isArray(report.highlights) && Array.isArray(report.uncertain)) {
    const evidenceText = new Map(packet.messages.map(message => [message.id, message.text]));
    report.highlights = report.highlights.filter(item => {
      const onlyQuestions = Array.isArray(item?.evidenceIds) && item.evidenceIds.length && item.evidenceIds.every(id => known.has(id) && questionOnly(evidenceText.get(id)));
      if (!onlyQuestions) return true;
      report.uncertain.push({ title: item.title, claim: item.text, whyUncertain: '现有证据只有提问，没有找到明确回答。', verification: '等待明确答复或查阅对应院校、课程或项目的官方资料。', evidenceIds: item.evidenceIds, links: item.links });
      return false;
    });
  }

  for (const role of roles) {
    const items = report[role];
    if (!Array.isArray(items)) throw Error(`日报 ${role} 结构无效`);
    if (section && role !== section && items.length) throw Error('单栏目编辑不能输出其他栏目');
    if (final && items.length > limits[role]) throw Error(`最终 ${role} 条目超过上限 ${limits[role]}`);
    if (extract && items.length > { highlights: 4, timeline: 2, uncertain: 3 }[role]) throw Error(`片段 ${role} 条目超过提取上限`);
    const allowed = candidates == null ? null : new Set(candidateItems(candidates, role).flatMap(item => item.evidenceIds || []));
    for (const item of items) {
      if (!item || typeof item !== 'object') throw Error('日报条目结构无效');
      requireText(item.title, '条目标题');
      if (!Array.isArray(item.evidenceIds) || !item.evidenceIds.length || !item.evidenceIds.every(id => typeof id === 'string' && known.has(id))) throw Error('日报条目缺少有效消息依据');
      if (allowed && !item.evidenceIds.every(id => allowed.has(id))) throw Error(`${role} 只能引用同栏目的候选证据，不能将待核实内容升格`);
      item.evidenceIds = [...new Set(item.evidenceIds)];
      let visible;
      if (role === 'highlights') {
        if (!categories.includes(item.category) || !kinds.includes(item.kind) || !['high', 'medium'].includes(item.confidence)) throw Error('精华分类或证据等级无效');
        requireText(item.text, '精华内容');
        requireText(item.basis, '精华依据');
        visible = ['title', 'text', 'basis'];
      } else if (role === 'timeline') {
        if (minute(item.endTime) < minute(item.startTime)) throw Error('讨论结束时间不能早于开始时间');
        if (minute(item.endTime) - minute(item.startTime) > 240) throw Error('单条讨论跨度超过 4 小时，请拆成更具体的话题');
        requireText(item.text, '讨论内容');
        if (!statuses.includes(item.status)) throw Error('讨论状态无效');
        if (!Array.isArray(item.keyPoints) || item.keyPoints.length < 2 || item.keyPoints.length > 4) throw Error('每条讨论需要 2 至 4 个要点');
        for (const point of item.keyPoints) requireText(point, '讨论要点');
        item.keyPoints = item.keyPoints.map(point => publicText(point, markers));
        visible = ['title', 'text'];
      } else {
        for (const key of ['claim', 'whyUncertain', 'verification']) requireText(item[key], '待核实说明');
        visible = ['title', 'claim', 'whyUncertain', 'verification'];
      }
      for (const key of visible) item[key] = publicText(item[key], markers);
      cleanLinks(item.links, markers);
    }
  }

  report.timeline.sort((a, b) => minute(a.startTime) - minute(b.startTime) || minute(a.endTime) - minute(b.endTime));
  if (final && candidates != null && (!section || section === 'timeline')) {
    const candidateTimeline = candidateItems(candidates, 'timeline');
    const needed = periods(candidateTimeline);
    const covered = periods(report.timeline);
    const names = ['00:00–09:00', '09:00–12:00', '12:00–18:00', '18:00–24:00'];
    const missing = [...needed].filter(value => !covered.has(value));
    if (missing.length) throw Error(`讨论脉络遗漏有候选内容的时段：${missing.map(value => names[value]).join('、')}`);
  }
  report.title = publicText(report.title, markers);
  report.summary = publicText(report.summary, markers);
  return report;
}

function mdText(value, inline = false) {
  let text = publicText(value);
  if (inline) text = text.replace(/\s+/g, ' ').trim();
  return text.replace(/[\\`*_\[\]{}#!|~]/g, '\\$&').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function addLinks(lines, links, indent = '') {
  for (const link of links) {
    const url = new URL(link.url).href.replace(/\(/g, '%28').replace(/\)/g, '%29');
    lines.push(`${indent}- [${mdText(link.title, true)}](${url})`);
  }
  if (links.length) lines.push('');
}

export function renderEditorialReport(report, packet) {
  validateEditorialReport(report, packet, { final: true });
  const lines = [`# ${packet.date} 保研与科研日报`, ''];
  if (report.summary.trim()) lines.push(mdText(report.summary), '');

  if (report.highlights.length) {
    lines.push('## 今日值得关注', '');
    for (const category of categories) {
      const items = report.highlights.filter(item => item.category === category);
      if (!items.length) continue;
      lines.push(`### ${category}`, '');
      for (const item of items) {
        lines.push(`- **${mdText(item.title, true)}**：${mdText(item.text, true)}`, '');
        addLinks(lines, item.links, '  ');
      }
    }
  }

  if (report.timeline.length) {
    lines.push('## 今日讨论脉络', '');
    for (const item of report.timeline) {
      const range = `${item.startTime}–${item.endTime}`;
      lines.push(`### ${range}｜${mdText(item.title, true)}`, '', mdText(item.text), '');
      for (const point of item.keyPoints) lines.push(`- ${mdText(point, true)}`);
      if (item.keyPoints.length) lines.push('');
      lines.push(`**讨论状态：** ${item.status}`, '');
      addLinks(lines, item.links);
    }
  }

  if (report.uncertain.length) {
    lines.push('## 传闻与待核实', '');
    for (const item of report.uncertain) {
      lines.push(`- **${mdText(item.title, true)}**：${mdText(item.claim, true)}`, `  - **不确定性：** ${mdText(item.whyUncertain, true)}`, `  - **建议核实：** ${mdText(item.verification, true)}`, '');
      addLinks(lines, item.links, '  ');
    }
  }

  if (!roles.some(role => report[role].length)) lines.push('今天已读取的消息中，没有筛选到符合主题的新信息。', '');
  const warnings = packet.coverage.filter(coverage => !coverage.boundaryReached || coverage.suspectedGaps?.length);
  lines.push('---', `本期根据 ${packet.messages.length} 条已返回消息整理。QQ 离线历史可能存在缺失。${warnings.length ? '本次检测到读取范围不足或疑似序号缺口。' : ''}${packet.coverage.some(coverage => coverage.unreadMedia) ? '图片、语音及未展开转发未纳入内容判断。' : ''}`, '');
  return lines.join('\n');
}
