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
