// Executed by the Qt smoke: one synthetic pairing code arrives only on stdin.
import assert from 'node:assert/strict';
import readline from 'node:readline/promises';
import {Client} from '../com.carter.youtube-music.sdPlugin/bin/client.mjs';
const input = readline.createInterface({input: process.stdin});
const line = await input[Symbol.asyncIterator]().next(); input.close();
const {port, code} = JSON.parse(line.value);
let saved;
const client = new Client({storage: async (executable, value) => {if (value.action === 'write') saved = value.credential; return saved;}});
const wait = async predicate => {
  const deadline = Date.now() + 10000;
  while (!predicate() && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10));
  assert.ok(predicate());
};
try {
  await client.pair(code, {port, executable: 'synthetic-vault'});
  assert.equal(client.credential.scope, 'control'); client.setActive(true); await wait(() => client.snapshot);
  for (const command of [{command: 'pause'}, {command: 'volume', value: 53}, {command: 'shuffle', value: true}, {command: 'repeat', mode: 'one'}, {command: 'seek', position: 10}, {command: 'like'}, {command: 'dislike'}]) await client.command(command);
  assert.equal(client.snapshot.playback.volume, 53); assert.equal(client.snapshot.playback.shuffle, true); assert.equal(client.snapshot.playback.repeat, 'one');
  process.stdout.write('revoke\n');
  await wait(() => client.status === 'Pair again');
  assert.equal(client.credential, null); assert.equal(client.snapshot, null);
  await assert.rejects(client.command({command: 'next'}));
  process.stdout.write('passed\n');
} finally { client.close(); }
