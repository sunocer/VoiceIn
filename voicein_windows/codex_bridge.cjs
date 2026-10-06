// Adapter for the installed Codex desktop application's version-specific IPC.
const net = require('node:net');
const crypto = require('node:crypto');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const threadId = input.threadId;
if (!/^[0-9a-f-]{36}$/.test(threadId || '')) throw Error('Codex thread UUID required');
const evidence = { threadId, sent: false };
const socket = net.createConnection('\\\\.\\pipe\\codex-ipc');
let clientId = 'initializing-client', buffer = Buffer.alloc(0);
const pending = new Map();
function write(message) {
  const body = Buffer.from(JSON.stringify(message), 'utf8');
  const header = Buffer.alloc(4); header.writeUInt32LE(body.length);
  socket.write(Buffer.concat([header, body]));
}
function rpc(method, params, version, targetClientId) {
  const requestId = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(requestId); reject(Error('Response timeout; do not resend automatically')); }, 20000);
    pending.set(requestId, { resolve, reject, timer });
    write({ type: 'request', requestId, sourceClientId: clientId, version, method, params,
      targetClientId, timeoutMs: 15000 });
  });
}
socket.on('error', error => {
  for (const item of pending.values()) { clearTimeout(item.timer); item.reject(error); }
  pending.clear();
});
socket.on('data', chunk => {
  buffer = Buffer.concat([buffer, chunk]);
  while (buffer.length >= 4) {
    const size = buffer.readUInt32LE(0);
    if (size > 268435456) { socket.destroy(); return; }
    if (buffer.length < 4 + size) break;
    const message = JSON.parse(buffer.subarray(4, 4 + size).toString('utf8'));
    buffer = buffer.subarray(4 + size);
    if (message.type === 'response' && pending.has(message.requestId)) {
      const item = pending.get(message.requestId); pending.delete(message.requestId);
      clearTimeout(item.timer); item.resolve(message);
    } else if (message.type === 'client-discovery-request') {
      write({ type: 'client-discovery-response', requestId: message.requestId, response: { canHandle: false } });
    }
  }
});
async function main() {
  await new Promise((resolve, reject) => { socket.once('connect', resolve); socket.once('error', reject); });
  const init = await rpc('initialize', { clientType: 'voicein-windows' }, 0);
  if (init.resultType !== 'success') throw Error(init.error || 'Codex IPC initialization failed');
  clientId = init.result.clientId;
  const owner = await rpc('thread-owner-discovery', { hostId: 'local', conversationId: threadId }, 1);
  if (owner.resultType !== 'success') throw Error(owner.error || 'No Codex desktop owner found');
  const text = input.text;
  if (typeof text !== 'string' || !text.trim() || text.length > 16000) throw Error('Invalid text');
  const id = input.commandId || crypto.randomUUID();
  const cwd = process.cwd();
  const restoreMessage = { id, text, cwd, createdAt: Date.now(), context: {
    prompt: text, addedFiles: [], fileAttachments: [], ideContext: null,
    imageAttachments: [], workspaceRoots: [cwd]
  }};
  evidence.sent = true;
  evidence.response = await rpc('thread-follower-steer-turn', {
    conversationId: threadId, input: [{ type: 'text', text, text_elements: [] }],
    clientUserMessageId: id, attachments: [], restoreMessage
  }, 1, owner.handledByClientId);
  if (evidence.response.resultType === 'error' &&
      /^Cannot steer conversation \S+ because its active turn already ended$/.test(evidence.response.error)) {
    evidence.response = await rpc('thread-follower-start-turn', { conversationId: threadId,
      turnStart: { request: { threadId, input: [{ type: 'text', text, text_elements: [] }],
        clientUserMessageId: id }, context: { inheritThreadSettings: true } }
    }, 2, owner.handledByClientId);
  }
  if (evidence.response.resultType !== 'success') throw Error(evidence.response.error || 'Codex rejected delivery');
}
main().catch(error => { evidence.error = error.message; process.exitCode = 1; }).finally(() => {
  socket.destroy();
  for (const item of pending.values()) clearTimeout(item.timer);
  console.log(JSON.stringify(evidence));
});
