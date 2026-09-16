import test from 'node:test';
import assert from 'node:assert/strict';
import { compactMessages, messageChunks } from '../model-input.mjs';

const message = (id, text) => ({ id, author: '成员abcdef', text, time: 1234567890, realSeq: '123', hasUnread: true });

test('compact input excludes only blank or known non-text placeholder messages', () => {
  const excluded = ['', ' \n\t', '[图片未识别][表情][引用]@群成员',
    '[语音未转录] [视频未识别]\n[群文件未读取][转发未展开][非文本内容未解析]'];
  const retained = ['[图片未识别] 截止时间今晚八点', '@群成员[引用]可以', '好',
    'https://example.org/material', '这个收费项目可能有问题', '[未知占位符]', '[邮箱]', '🙂'];
  const input = [...excluded, ...retained].map((text, i) => message(String(i), text));
  const snapshot = structuredClone(input);
  assert.deepEqual(compactMessages(input).map(m => m.text), retained);
  assert.deepEqual(input, snapshot, 'compaction must not mutate the local evidence packet');
});

test('compaction preserves evidence IDs, anonymous authors, order and original text', () => {
  const input = [message('m_first', ' 文字\n[图片未识别] '), message('m_second', 'x')];
  assert.deepEqual(compactMessages(input), [
    { id: 'm_first', author: '成员abcdef', text: ' 文字\n[图片未识别] ', time: '07:31:30' },
    { id: 'm_second', author: '成员abcdef', text: 'x', time: '07:31:30' },
  ]);
});

test('message times retain Shanghai clock context without changing the evidence packet', () => {
  const input = [
    { ...message('morning', '今天11点前确认'), time: Date.parse('2026-09-14T23:37:04Z') / 1000 },
    { ...message('midnight', '今天开始'), time: Date.parse('2026-09-14T16:00:00Z') / 1000 },
    { ...message('evening', '明天提交'), time: Date.parse('2026-09-15T15:59:59Z') / 1000 },
    { id: 'untimed', author: '成员abcdef', text: '无时间的测试消息' },
  ];
  const snapshot = structuredClone(input), compact = compactMessages(input);
  assert.deepEqual(compact.map(m => m.time), ['07:37:04', '00:00:00', '23:59:59', undefined]);
  assert.deepEqual(input, snapshot);
});

test('chunk sizes include JSON escaping, commas and array brackets', () => {
  const input = compactMessages([message('1', '引号"\n\\🙂'), message('2', '短句'), message('3', '末条')]);
  const exactLimit = JSON.stringify(input.slice(0, 2)).length;
  assert.deepEqual(messageChunks(input, exactLimit), [input.slice(0, 2), input.slice(2)]);
  const smaller = messageChunks(input, exactLimit - 1);
  assert.equal(smaller[0].length, 1);
  assert.deepEqual(smaller.flat(), input);
  for (const chunk of smaller) assert.ok(JSON.stringify(chunk).length <= exactLimit - 1);
});

test('oversized individual messages stay complete and alone', () => {
  const input = compactMessages([message('1', '前'), message('2', '长'.repeat(400)), message('3', '后')]);
  const chunks = messageChunks(input, 100);
  assert.deepEqual(chunks, [[input[0]], [input[1]], [input[2]]]);
  assert.equal(chunks[1][0].text.length, 400);
  assert.deepEqual(chunks.flat(), input);
});

test('empty or fully non-text input creates no model calls', () => {
  assert.deepEqual(compactMessages([]), []);
  assert.deepEqual(messageChunks([]), []);
  assert.deepEqual(messageChunks(compactMessages([message('1', '[表情]')])), []);
  for (const invalid of [0, -1, 1.5, Infinity, NaN]) assert.throws(() => messageChunks([], invalid), RangeError);
});
