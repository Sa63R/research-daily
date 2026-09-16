import test from 'node:test';
import assert from 'node:assert/strict';
import { validateEditorialReport, renderEditorialReport } from '../editorial.mjs';

const ids = ['m_111111111111111111111111', 'm_222222222222222222222222', 'm_333333333333333333333333', 'm_444444444444444444444444'];
function packet() {
  return { date: '2026-09-15', messages: ids.map((id, index) => ({ id, author: `成员a1b2c${index}`, text: '有群友反馈某学院系统已显示复试安排。' })), coverage: [{ group: '123456789', boundaryReached: true, suspectedGaps: [], unreadMedia: 0 }] };
}
function report() { return { schemaVersion: 2, title: '保研与科研日报', summary: '考核安排与科研学习讨论。', highlights: [], timeline: [], uncertain: [] }; }
function highlight(id = ids[0]) { return { category: '院校与项目', title: '某学院复试安排', text: '有群友反馈系统已显示复试安排，适用范围限该学院。', kind: '动态', confidence: 'medium', basis: '群友亲历，未独立核实', evidenceIds: [id], links: [] }; }
function topic(startTime = '08:30', endTime = '08:50', id = ids[1]) { return { startTime, endTime, title: '核对考核安排', text: '讨论从短信是否到达转向查询系统，随后澄清了不同批次的适用范围。', keyPoints: ['有群友先在系统看到安排。', '后续答复明确不同批次不能混用。'], status: '已有答复', evidenceIds: [id], links: [] }; }
function uncertain(id = ids[2]) { return { title: '尚未确认的候补安排', claim: '有群友转述可能有新一轮候补通知。', whyUncertain: '只有单一转述，未见正式通知。', verification: '核对本人批次的学院正式通知。', evidenceIds: [id], links: [] }; }

test('editorial evidence cannot be fabricated or promoted from uncertain to highlights', () => {
  const input = packet(), candidates = report();
  candidates.highlights = [highlight()]; candidates.uncertain = [uncertain()];
  const edited = report(); edited.highlights = [highlight(ids[2])];
  assert.throws(() => validateEditorialReport(edited, input, { candidates, final: true }), /同栏目/);
  edited.highlights[0].evidenceIds = ['m_fabricated'];
  assert.throws(() => validateEditorialReport(edited, input), /有效消息依据/);
  edited.highlights[0].evidenceIds = [ids[0]];
  assert.doesNotThrow(() => validateEditorialReport(edited, input, { candidates, section: 'highlights', final: true }));
});

test('section editing cannot populate another role; overview contains no entries', () => {
  const input = packet(), edited = report(); edited.highlights = [highlight()];
  assert.throws(() => validateEditorialReport(edited, input, { section: 'timeline' }), /其他栏目/);
  assert.throws(() => validateEditorialReport(edited, input, { section: 'overview' }), /其他栏目/);
  edited.highlights = [];
  assert.doesNotThrow(() => validateEditorialReport(edited, input, { section: 'overview' }));
});

test('timeline preserves active candidate periods, sorts chronologically and permits a quiet day', () => {
  const input = packet(), candidates = report();
  candidates.timeline = [topic('08:50', '09:10'), topic('13:00', '13:20', ids[2]), topic('20:00', '20:20', ids[3])];
  const edited = report(); edited.timeline = [topic('20:00', '20:20', ids[3]), topic('13:00', '13:20', ids[2]), topic('09:00', '09:10')];
  assert.throws(() => validateEditorialReport(edited, input, { candidates, section: 'timeline', final: true }), /00:00–09:00/);
  edited.timeline[0].startTime = '08:50';
  assert.doesNotThrow(() => validateEditorialReport(edited, input, { candidates, section: 'timeline', final: true }));
  assert.deepEqual(edited.timeline.map(item => item.startTime), ['08:50', '13:00', '20:00']);
  const quiet = report();
  assert.doesNotThrow(() => validateEditorialReport(quiet, input, { candidates: report(), final: true }));
  const highlightsOnly = report(); highlightsOnly.highlights = [highlight()]; candidates.highlights = [highlight()];
  assert.doesNotThrow(() => validateEditorialReport(highlightsOnly, input, { candidates, section: 'highlights', final: true }), 'editing highlights must not demand a timeline');
});

test('timeline rejects invalid times, overlong spans and missing discussion detail', () => {
  const input = packet(), edited = report(); edited.timeline = [topic('25:00', '25:30')];
  assert.throws(() => validateEditorialReport(edited, input), /HH:mm/);
  edited.timeline = [topic('10:00', '09:00')];
  assert.throws(() => validateEditorialReport(edited, input), /早于/);
  edited.timeline = [topic('08:00', '12:01')];
  assert.throws(() => validateEditorialReport(edited, input), /4 小时/);
  edited.timeline = [topic()]; edited.timeline[0].keyPoints = ['只有标题式概述'];
  assert.throws(() => validateEditorialReport(edited, input), /2 至 4/);
});

test('extraction moves question-only evidence to uncertain without suppressing comparisons or methods', () => {
  const input = packet();
  input.messages[0].text = '请问某学院软件专硕已经发复试通知了吗？';
  input.messages[1].text = '如何复现是这门课实际演示过的内容，材料包含推理代码。';
  input.messages[2].text = '某学院同一批次有两位群友报告排名前10%入围，也有未入围样本，不能推断统一门槛。';
  const extracted = report(); extracted.highlights = [highlight(ids[0]), highlight(ids[1]), highlight(ids[2])];
  validateEditorialReport(extracted, input, { extract: true });
  assert.deepEqual(extracted.highlights.map(item => item.evidenceIds[0]), [ids[1], ids[2]]);
  assert.equal(extracted.uncertain.length, 1);
  assert.match(extracted.uncertain[0].whyUncertain, /只有提问/);
  const tooMany = report(); tooMany.timeline = [topic(), topic(), topic()];
  assert.throws(() => validateEditorialReport(tooMany, input, { extract: true }), /提取上限/);
});

test('editorial public text and links remove private identifiers from every role', () => {
  const input = packet(), edited = report();
  const secret = `123456789 ${ids[0]} 成员a1b2c0 13812345678 user@example.com`;
  edited.title = edited.summary = secret;
  const main = highlight(); main.title = main.text = main.basis = secret;
  const sequence = topic(); sequence.title = sequence.text = secret; sequence.keyPoints = [secret, secret];
  const unconfirmed = uncertain(); unconfirmed.title = unconfirmed.claim = unconfirmed.whyUncertain = unconfirmed.verification = secret;
  for (const item of [main, sequence, unconfirmed]) item.links = [{ title: secret, url: 'https://arxiv.org/abs/2609.15128' }];
  edited.highlights = [main]; edited.timeline = [sequence]; edited.uncertain = [unconfirmed];
  const markdown = renderEditorialReport(edited, input);
  for (const value of ['123456789', ids[0], '成员a1b2c0', '13812345678', 'user@example.com']) assert.ok(!markdown.includes(value), value);
  for (const item of [main, sequence, unconfirmed]) assert.ok(!item.links[0].title.includes('user@example.com'));
  assert.ok(!main.basis.includes('123456789'), 'internal provenance is sanitized too');
  assert.equal(renderEditorialReport(edited, input), markdown, 'rendering should remain stable');
  unconfirmed.links[0].url = 'https://example.com/?token=private';
  assert.throws(() => validateEditorialReport(edited, input), /身份或凭据/);
});

test('rendering follows the source report roles and never forces action steps or publishes evidence IDs', () => {
  const input = packet(), edited = report();
  edited.highlights = [highlight()]; edited.timeline = [topic()]; edited.uncertain = [uncertain()];
  edited.highlights[0].text += ' ![图片](https://example.com/pixel.png) <script>alert(1)</script>';
  input.coverage[0].suspectedGaps = [{ from: '10', to: '11' }]; input.coverage[0].unreadMedia = 1;
  const markdown = renderEditorialReport(edited, input);
  assert.match(markdown, /## 今日值得关注/); assert.match(markdown, /### 院校与项目/);
  assert.match(markdown, /## 今日讨论脉络/); assert.match(markdown, /08:30–08:50｜核对考核安排/);
  assert.match(markdown, /\*\*讨论状态：\*\* 已有答复/); assert.match(markdown, /## 传闻与待核实/);
  assert.match(markdown, /疑似序号缺口/); assert.match(markdown, /图片、语音及未展开转发未纳入/);
  for (const value of ['怎么开始', '轻松一刻', 'confidence', '<script>', '![图片]', ...ids]) assert.ok(!markdown.includes(value), value);
});
