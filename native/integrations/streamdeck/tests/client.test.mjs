import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {Client, DEFAULTS, request, settings} from '../com.carter.youtube-music.sdPlugin/bin/client.mjs';
import {ACTIONS, UUID, Plugin, actionCommand, title} from '../com.carter.youtube-music.sdPlugin/bin/plugin.mjs';
const credential = {port: 9864, clientId: 'a'.repeat(32), token: 's'.repeat(43), scope: 'control'};
const state = {version: 1, revision: 4, playback: {state: 'playing', volume: 40, position: 15, duration: 120, shuffle: false, repeat: 'off'}, capabilities: {play: true, seek: true, next: true, previous: true, rate: true}, track: {title: 'Synthetic track', artists: ['Fixture artist']}};
const settle = () => new Promise(resolve => setImmediate(resolve));
function harness(options = {}) {
  const calls = [], saves = [], timers = [], storage = [];
  const client = new Client({send: async (...args) => {calls.push(args); return args[1] === '/v1/pair' ? credential : structuredClone(state);}, storage: async (...args) => {storage.push(args); return credential;}, schedule: (fn, delay) => { const timer = {fn, delay}; timers.push(timer); return timer; }, cancel: timer => {if (timer) timer.cancelled = true;}, onSettings: value => saves.push({...value}), ...options});
  return {client, calls, saves, timers, storage};
}
test('unpaired and invisible plugin is idle; saved control credential resumes only with visible actions', async () => {
  const h = harness(); await h.client.configure(DEFAULTS); h.client.setActive(true); await settle();
  assert.equal(h.calls.length, 0); assert.equal(h.storage.length, 0);
  h.client.setActive(false); await h.client.configure({...DEFAULTS, autoConnect: true});
  assert.equal(h.calls.length, 0); h.client.setActive(true); await settle();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0][2].token, credential.token); assert.equal(h.client.status, 'Connected');
  h.client.setActive(false); assert.equal(h.timers.at(-1).cancelled, true); h.client.close();
});
test('pairing persists the token only in OS storage, with settings limited to public preferences', async () => {
  const h = harness(); await h.client.pair('c'.repeat(24), DEFAULTS);
  assert.equal(h.client.credential.token, credential.token);
  assert.equal(h.storage[0][1].credential.token, credential.token);
  assert.equal(h.saves.at(-1).autoConnect, true);
  assert.ok(!JSON.stringify(h.saves).includes(credential.token)); assert.ok(!JSON.stringify(h.saves).includes('clientId'));
  await h.client.forget(); assert.equal(h.client.credential, null); assert.equal(h.saves.at(-1).autoConnect, false); assert.equal(h.storage.at(-1)[1].action, 'delete');
});
test('keyring failure and read-only pairing fail closed without a plaintext fallback', async () => {
  const h = harness({storage: async () => {throw new Error('Keyring unavailable.');}});
  await h.client.pair('c'.repeat(24), DEFAULTS); assert.equal(h.client.credential, null); assert.equal(h.saves.at(-1).autoConnect, false); assert.match(h.client.detail, /Revoke/);
  const readOnly = harness({send: async () => ({...credential, scope: 'overlay'})});
  await readOnly.client.pair('c'.repeat(24), DEFAULTS); assert.equal(readOnly.storage.length, 0); assert.equal(readOnly.client.credential, null);
});
test('revocation stops reconnects and commands until an explicit new pairing', async () => {
  const h = harness({send: async () => {throw Object.assign(new Error(), {status: 401});}});
  await h.client.configure({...DEFAULTS, autoConnect: true}); h.client.setActive(true); await settle();
  assert.equal(h.client.credential, null); assert.equal(h.timers.length, 0); assert.equal(h.client.status, 'Pair again');
  await assert.rejects(h.client.command({command: 'next'})); assert.equal(h.saves.at(-1).autoConnect, false);
});
test('offline retry has bounded backoff and closes without stale responses or pending timers', async () => {
  const h = harness({send: async () => {throw new Error('offline');}});
  await h.client.configure({...DEFAULTS, autoConnect: true}); h.client.setActive(true); await settle();
  for (let i = 0; i < 8; i++) { await h.timers.at(-1).fn(); }
  assert.deepEqual(h.timers.slice(0, 6).map(t => t.delay), [1000, 2000, 4000, 8000, 16000, 30000]);
  assert.ok(h.timers.every(t => t.delay <= 30000)); h.client.close(); assert.equal(h.timers.at(-1).cancelled, true);
  let resolve; const stale = harness({send: () => new Promise(done => {resolve = done;})});
  await stale.client.configure({...DEFAULTS, autoConnect: true}); stale.client.setActive(true); stale.client.close(); resolve(state); await settle();
  assert.equal(stale.client.snapshot, null); assert.equal(stale.timers.length, 0);
});
test('command failure is never automatically replayed; concurrent actions fail visibly', async () => {
  let calls = 0; const h = harness({send: async () => {calls++; throw new Error('timeout');}});
  h.client.credential = credential; h.client.snapshot = structuredClone(state);
  await assert.rejects(h.client.command({command: 'next'})); assert.equal(calls, 1); assert.equal(h.timers.length, 0); assert.match(h.client.detail, /never replayed/);
  h.client.busy = true; await assert.rejects(h.client.command({command: 'next'})); assert.equal(calls, 1);
});
test('all action families reuse API commands, honor capabilities and bound absolute volume', () => {
  for (const name of Object.keys(ACTIONS)) assert.ok(actionCommand(name, state).command);
  assert.deepEqual(actionCommand('shuffle', state), {command: 'shuffle', value: true});
  assert.deepEqual(actionCommand('repeat', state), {command: 'cycleRepeat'});
  assert.deepEqual(actionCommand('volume', state, 100), {command: 'volume', value: 80});
  assert.deepEqual(actionCommand('volume-down', {...state, playback: {...state.playback, volume: 2}}), {command: 'volume', value: 0});
  assert.deepEqual(actionCommand('volume-up', {...state, playback: {...state.playback, volume: 98}}), {command: 'volume', value: 100});
  assert.throws(() => actionCommand('like', {...state, capabilities: {rate: false}})); assert.throws(() => actionCommand('shell', state));
  assert.match(title('track', {snapshot: state}), /Synthetic track\nFixture artist/);
});
test('WebSocket registration and key release dispatch once; inspectors never receive credentials', async () => {
  const sent = [], socket = {readyState: 1, send: value => sent.push(JSON.parse(value))};
  const plugin = new Plugin(socket, {event: 'registerPlugin', uuid: 'fixture'}, {schedule: () => null, cancel() {}});
  plugin.start(); assert.equal(sent[0].event, 'registerPlugin'); assert.equal(sent[1].event, 'getGlobalSettings');
  await plugin.receive({event: 'willAppear', context: 'key', action: UUID + '.next', payload: {controller: 'Keypad'}});
  plugin.client.credential = credential; plugin.client.snapshot = structuredClone(state);
  const commands = []; plugin.client.command = async command => commands.push(command);
  await plugin.receive({event: 'keyDown', context: 'key', action: UUID + '.next'});
  await plugin.receive({event: 'keyUp', context: 'key', action: UUID + '.next'});
  assert.deepEqual(commands, [{command: 'next'}]);
  await plugin.receive({event: 'propertyInspectorDidAppear', context: 'key', action: UUID + '.next'});
  assert.ok(!JSON.stringify(sent).includes(credential.token));
  plugin.client.snapshot = null; await plugin.receive({event: 'keyUp', context: 'key', action: UUID + '.next'}); assert.equal(sent.at(-1).event, 'showAlert');
  plugin.close(); assert.equal(plugin.actions.size, 0);
});
test('echoed global settings cannot cancel an in-flight pairing', async () => {
  const sent = [], plugin = new Plugin({readyState: 1, send: text => sent.push(JSON.parse(text))}, {event: 'registerPlugin', uuid: 'fixture'}, {send: async () => credential, storage: async () => null});
  await plugin.receive({event: 'willAppear', context: 'key', action: UUID + '.next'});
  plugin.client.setActive(false);
  await plugin.client.pair('c'.repeat(24), DEFAULTS);
  const generation = plugin.client.generation;
  await plugin.receive({event: 'didReceiveGlobalSettings', payload: {settings: {...DEFAULTS, autoConnect: false}}});
  await plugin.receive({event: 'didReceiveGlobalSettings', payload: {settings: sent.filter(row => row.event === 'setGlobalSettings').at(-1).payload}});
  assert.equal(plugin.client.generation, generation); assert.equal(plugin.client.credential.token, credential.token); plugin.close();
});
test('loopback transport sends credentials only as headers and rejects redirects, oversized and invalid responses', async t => {
  const server = http.createServer((req, res) => {
    assert.equal(req.headers.host, `127.0.0.1:${server.address().port}`);
    if (req.url === '/ok') {assert.equal(req.headers.authorization, 'Bearer ' + credential.token); res.end(JSON.stringify(state));}
    else if (req.url === '/redirect') {res.writeHead(302, {Location: 'https://example.invalid'}); res.end();}
    else if (req.url === '/large') res.end('x'.repeat(70000));
    else res.end('not JSON');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); t.after(() => server.close()); const port = server.address().port;
  assert.equal((await request(port, '/ok', {token: credential.token})).version, 1);
  for (const path of ['/redirect', '/large', '/invalid']) await assert.rejects(request(port, path));
  assert.throws(() => settings({port: 80, executable: 'app'})); assert.throws(() => settings({port: 9864, executable: 'bad\ncommand'}));
});


test('late event snapshots cannot replace a newer command refresh and malformed refreshes fail closed', async () => {
  let finishPoll;
  const h = harness({send: async (port, path) => {
    if (path.startsWith('/v1/events')) return new Promise(resolve => {finishPoll = resolve;});
    return {...structuredClone(state), revision: 6, playback: {...state.playback, volume: 50}};
  }});
  h.client.credential = credential; h.client.snapshot = structuredClone(state); h.client.active = true;
  const polling = h.client.poll(); await h.client.command({command: 'volume', value: 50});
  finishPoll({...structuredClone(state), revision: 5}); await polling;
  assert.equal(h.client.snapshot.revision, 6); assert.equal(h.client.snapshot.playback.volume, 50); h.client.close();
  const bad = harness({send: async (port, path) => path === '/v1/command' ? {ok: true} : {...state, playback: null}});
  bad.client.credential = credential; bad.client.snapshot = state;
  await assert.rejects(bad.client.command({command: 'next'})); assert.equal(bad.client.snapshot, null);
});

test('rapid volume dial ticks coalesce behind an in-flight command without losing input', async () => {
  let release, volume = 40, revision = 4; const commands = [];
  const plugin = new Plugin({readyState: 1, send() {}}, {event: 'registerPlugin', uuid: 'fixture'}, {send: async (port, path, options) => {
    if (path === '/v1/command') {
      commands.push(options.body); if (commands.length === 1) await new Promise(resolve => {release = resolve;});
      volume = options.body.value; revision++; return {ok: true};
    }
    return {...structuredClone(state), revision, playback: {...state.playback, volume}};
  }});
  plugin.client.credential = credential; plugin.client.snapshot = structuredClone(state);
  const first = plugin.adjustVolume(2, 'dial'); await settle();
  const second = plugin.adjustVolume(4, 'dial'); const third = plugin.adjustVolume(4, 'dial');
  release(); await Promise.all([first, second, third]);
  assert.deepEqual(commands.map(command => command.value), [42, 50]); assert.equal(plugin.client.snapshot.playback.volume, 50); plugin.close();
});

test('revocation during a command aborts polling and disables reconnect immediately', async () => {
  const h = harness({send: async () => {throw Object.assign(new Error(), {status: 403});}});
  h.client.credential = credential; h.client.snapshot = state;
  await assert.rejects(h.client.command({command: 'next'}));
  assert.equal(h.client.credential, null); assert.equal(h.client.snapshot, null); assert.equal(h.client.status, 'Pair again');
});

test('settings UI preserves unsaved fields, clears pairing codes, and renders metadata as text', async () => {
  const {readFileSync} = await import('node:fs');
  const {runInNewContext} = await import('node:vm');
  const elements = Object.fromEntries(['pairing', 'port', 'executable', 'code', 'pair', 'reconnect', 'forget', 'status', 'detail', 'track', 'position'].map(name => [name, {value: '', textContent: '', disabled: false}]));
  const sent = []; let socket;
  class FakeSocket { constructor() {this.readyState = 1; socket = this;} send(text) {sent.push(JSON.parse(text));} }
  const window = {}, document = {getElementById: id => elements[id]};
  const source = readFileSync(new URL('../com.carter.youtube-music.sdPlugin/ui/settings.js', import.meta.url), 'utf8');
  runInNewContext(source, {window, document, WebSocket: FakeSocket, JSON, Number});
  window.connectElgatoStreamDeckSocket(1234, 'inspector', 'registerPropertyInspector', '{}', JSON.stringify({context: 'key', action: UUID + '.next'}));
  socket.onopen();
  const update = value => socket.onmessage({data: JSON.stringify({event: 'sendToPropertyInspector', payload: {options: DEFAULTS, status: 'Connected', detail: '', track: '<b>plain metadata</b>', ...value}})});
  update({}); elements.executable.value = '/New App/native'; elements.port.value = '9865';
  update({position: '10 seconds'});
  assert.equal(elements.executable.value, '/New App/native'); assert.equal(elements.port.value, '9865');
  assert.equal(elements.track.textContent, '<b>plain metadata</b>');
  elements.code.value = 'c'.repeat(24); elements.pairing.onsubmit({preventDefault() {}});
  assert.equal(elements.code.value, ''); assert.equal(sent.at(-1).payload.options.executable, '/New App/native');
  assert.ok(sent.every(message => message.event !== 'setGlobalSettings'));
});


test('API restart changes epoch while late responses from the old server stay ignored', () => {
  const {client} = harness(); const first = 'a'.repeat(32), second = 'b'.repeat(32);
  client.acceptSnapshot({...state, instanceId: first, revision: 900});
  assert.equal(client.acceptSnapshot({...state, instanceId: second, revision: 1}, first), true);
  assert.equal(client.snapshot.instanceId, second);
  assert.equal(client.acceptSnapshot({...state, instanceId: first, revision: 901}, first), false);
  assert.equal(client.snapshot.instanceId, second); assert.equal(client.snapshot.revision, 1);
  assert.equal(client.acceptSnapshot({...state, instanceId: second, revision: 0}, second), false);
  assert.equal(client.acceptSnapshot({...state, instanceId: second, revision: 2}, second), true);
});
