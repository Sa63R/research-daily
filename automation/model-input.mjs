// These are the non-text placeholders emitted by normalize(). Unknown bracketed
// text remains meaningful input; do not infer topics or usefulness here.
const nonTextPlaceholders = /\[(?:图片未识别|语音未转录|视频未识别|群文件未读取|转发未展开|非文本内容未解析|表情|引用)\]|@群成员/g;
const localClock = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

export function compactMessages(messages) {
  return messages
    .filter(message => message.text.replace(nonTextPlaceholders, '').trim().length > 0)
    .map(({ id, author, text, time }) => ({
      id, author, text,
      ...(time == null ? {} : { time: localClock.format(new Date(Number(time) * 1000)) }),
    }));
}

// The limit covers the serialized messages array, including brackets, commas
// and JSON escapes. Callers must budget separately for their prompt/envelope.
// Empty input returns []; an oversized message remains intact in its own chunk.
export function messageChunks(messages, maxChars = 140000) {
  if (!Number.isSafeInteger(maxChars) || maxChars <= 0) {
    throw new RangeError('maxChars must be a positive safe integer');
  }
  const chunks = [];
  let chunk = [], size = 2;
  for (const message of messages) {
    const length = JSON.stringify(message).length;
    if (chunk.length && size + 1 + length > maxChars) {
      chunks.push(chunk);
      chunk = [];
      size = 2;
    }
    size += length + (chunk.length ? 1 : 0);
    chunk.push(message);
  }
  if (chunk.length) chunks.push(chunk);
  return chunks;
}

// Match the upstream editor's 20k-character / 400-message windows and keep
// 20 messages of context across cuts. Character accounting covers the readable
// chat transcript rather than JSON keys and opaque local evidence IDs.
export function editorialChunks(messages, { maxChars = 20000, maxMessages = 400, overlapMessages = 20 } = {}) {
  if (![maxChars, maxMessages, overlapMessages].every(Number.isSafeInteger) || maxChars <= 0 || maxMessages <= 0 || overlapMessages < 0 || overlapMessages >= maxMessages) throw new RangeError('Invalid editorial chunk limits');
  const chunks = [];
  let start = 0;
  while (start < messages.length) {
    let end = start, size = 0;
    while (end < messages.length && end - start < maxMessages) {
      const message = messages[end];
      const length = `${message.time || ''} ${message.author || ''}: ${message.text}`.length + 1;
      if (end > start && size + length > maxChars) break;
      size += length;
      end++;
    }
    chunks.push(messages.slice(start, end));
    if (end === messages.length) break;
    // A single oversized message must still advance the next window.
    start = Math.max(start + 1, end - overlapMessages);
  }
  return chunks;
}

export function validateTimelineEvidenceTimes(report, packet) {
  const messages = new Map(packet.messages.map(message => [message.id, message]));
  for (const topic of report.timeline || []) {
    const times = topic.evidenceIds.map(id => messages.get(id)?.time).filter(time => Number.isFinite(time))
      .map(time => localClock.format(new Date(time * 1000)).slice(0, 5));
    if (times.length && !times.some(time => time >= topic.startTime && time <= topic.endTime)) {
      throw Error(`讨论“${topic.title}”的 ${topic.startTime}–${topic.endTime} 与引用消息时间不符，请依据消息校正时间`);
    }
  }
  return report;
}
