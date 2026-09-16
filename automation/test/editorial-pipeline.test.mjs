import test from 'node:test';
import assert from 'node:assert/strict';
import { editorialChunks, validateTimelineEvidenceTimes } from '../model-input.mjs';
import { generateEditorialReport, emptyEditorialReport } from '../editorial-pipeline.mjs';

const day = '2026-09-15';
const message = (id, hour = 10, text = '某学院发布了考核安排') => ({ id, time: Date.parse(`${day}T${String(hour).padStart(2, '0')}:00:00+08:00`) / 1000, text });
const packet = { date: day, messages: [message('a'), message('b'), message('c')], coverage: [] };
const blank = () => ({ ...emptyEditorialReport(), title: '测试日报', summary: '考核安排与问题澄清。' });
const highlight = id => ({ category: '院校与项目', title: '某学院发布考核安排', text: '群内转述了考核安排，尚未独立核实。', kind: '动态', confidence: 'medium', basis: '群内转述', evidenceIds: [id], links: [] });
const timeline = id => ({ startTime: '10:00', endTime: '10:00', title: '考核安排讨论', text: '讨论了考核环节。', keyPoints: ['提出了日期问题', '尚未取得官方材料'], status: '没有结论', evidenceIds: [id], links: [] });
const uncertain = id => ({ title: '考核批次待确认', claim: '消息可能涉及不同批次。', whyUncertain: '缺少批次信息。', verification: '查看对应批次学院通知。', evidenceIds: [id], links: [] });

test('editorial windows preserve overlap, every message, and forward progress', () => {
  const messages = Array.from({ length: 9 }, (_, i) => message(String(i)));
  const chunks = editorialChunks(messages, { maxChars: 10000, maxMessages: 4, overlapMessages: 1 });
  assert.deepEqual(chunks.map(chunk => chunk.map(item => item.id)), [['0','1','2','3'], ['3','4','5','6'], ['6','7','8']]);
  assert.equal(editorialChunks([message('huge', 10, 'x'.repeat(500)), message('small')], { maxChars: 1 }).length, 2);
  assert.throws(() => editorialChunks(messages, { maxMessages: 2, overlapMessages: 2 }));
});

test('single-batch days still receive independent section editing and overview', async () => {
  const calls = [];
  const report = await generateEditorialReport(packet, { summarize: async (input, suffix, options) => {
    calls.push({ input, suffix, options });
    if (input.stage === 'extract') return { ...blank(), highlights: [highlight('a')], timeline: [timeline('b')], uncertain: [uncertain('c')] };
    if (input.stage === 'edit') {
      for (const candidate of input.candidates) for (const role of ['highlights', 'timeline', 'uncertain']) if (role !== input.section) assert.equal(candidate[role].length, 0);
      assert.equal(options.final, true);
      assert.ok(input.crossRoleReview.candidates);
      if(input.section==='highlights')assert.equal(input.crossRoleReview.candidates.uncertain[0].claim,'消息可能涉及不同批次。');
      return { ...blank(), [input.section]: input.candidates.flatMap(candidate => candidate[input.section]) };
    }
    assert.ok(input.report.highlights.length);
    return { ...blank(), summary: '编辑后的导读。' };
  } });
  assert.equal(report.summary, '编辑后的导读。');
  assert.equal(calls.filter(call => call.input.stage === 'edit').length, 3);
  assert.equal(calls.at(-1).input.stage, 'overview');
});

test('an evening message cannot fabricate morning discussion coverage', () => {
  const report = { ...blank(), timeline: [timeline('evening')] };
  assert.throws(() => validateTimelineEvidenceTimes(report, { ...packet, messages: [message('evening', 21)] }), /时间不符/);
  report.timeline[0].startTime='21:00'; report.timeline[0].endTime='21:01';
  assert.doesNotThrow(() => validateTimelineEvidenceTimes(report, { ...packet, messages: [message('evening', 21)] }));
});

test('an editor cannot promote a pending question into highlights', async () => {
  await assert.rejects(generateEditorialReport(packet, { summarize: async input => {
    if (input.stage === 'extract') return { ...blank(), highlights: [highlight('a')], uncertain: [uncertain('c')] };
    if (input.section === 'highlights') return { ...blank(), highlights: [highlight('c')] };
    return { ...blank(), [input.section]: input.candidates.flatMap(candidate => candidate[input.section]) };
  } }));
});

test('extraction evidence must come from the actual chunk, not another batch', async () => {
  await assert.rejects(generateEditorialReport(packet, { chunkOptions: { maxMessages: 1, overlapMessages: 0 }, summarize: async input => ({ ...blank(), highlights: [highlight(input.messages[0].id === 'a' ? 'b' : 'a')] }) }));
});

test('unread media alone never triggers fabricated text summaries', async () => {
  const result = await generateEditorialReport({ ...packet, messages: [message('image', 10, '[图片未识别]')] }, { summarize: async () => { throw Error('must not call model'); } });
  assert.deepEqual(result.highlights, []);
  assert.match(result.summary, /没有可供整理的文字/);
});
