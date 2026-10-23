import {pathToFileURL} from 'node:url';
import {Client, DEFAULTS, settings} from './client.mjs';
export const UUID = 'com.carter.youtube-music';
export const ACTIONS = Object.freeze({toggle: 'Play / Pause', play: 'Play', pause: 'Pause', previous: 'Previous', next: 'Next', stop: 'Stop', like: 'Like', dislike: 'Dislike', shuffle: 'Shuffle', repeat: 'Repeat', 'volume-up': 'Volume +', 'volume-down': 'Volume −', volume: 'Volume / Mute', track: 'Now Playing'});
const clean = (value, limit = 40) => typeof value === 'string' ? value.replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, limit) : '';
export function actionCommand(action, snapshot, ticks) {
  if (!snapshot?.playback || !snapshot.capabilities) throw new Error('Player disconnected.');
  const p = snapshot.playback, c = snapshot.capabilities;
  if (['play', 'pause', 'toggle', 'stop'].includes(action) && !c.play || ['next', 'previous'].includes(action) && !c[action] || ['like', 'dislike'].includes(action) && !c.rate) throw new Error('Action unavailable.');
  if (action === 'shuffle') return {command: 'shuffle', value: !p.shuffle};
  if (action === 'repeat') return {command: 'cycleRepeat'};
  if (action === 'track') return {command: 'show'};
  if (action === 'volume' && ticks === undefined) return {command: 'mute'};
  if (['volume-up', 'volume-down', 'volume'].includes(action)) {
    const delta = action === 'volume' ? Math.max(-20, Math.min(20, Number(ticks))) * 2 : action === 'volume-up' ? 5 : -5;
    if (!Number.isFinite(delta) || !Number.isFinite(p.volume)) throw new Error('Invalid volume.');
    return {command: 'volume', value: Math.max(0, Math.min(100, p.volume + delta))};
  }
  if (Object.hasOwn(ACTIONS, action)) return {command: action};
  throw new Error('Unknown action.');
}
export function title(action, client) {
  const state = client.snapshot;
  if (!state) return `${ACTIONS[action]}\n${client.status === 'Offline' ? 'Offline' : 'Connect'}`;
  const p = state.playback;
  if (action === 'track') return state.track ? `${clean(state.track.title, 28)}\n${clean(state.track.artists?.join(' · '), 24)}` : 'Nothing\nplaying';
  if (action === 'toggle') return p.state === 'playing' ? 'Pause' : 'Play';
  if (action === 'shuffle') return `Shuffle\n${p.shuffle ? 'On' : 'Off'}`;
  if (action === 'repeat') return `Repeat\n${clean(p.repeat, 8)}`;
  if (action.startsWith('volume')) return `${ACTIONS[action]}\n${Math.round(p.volume)}%`;
  return ACTIONS[action];
}
export class Plugin {
  constructor(socket, registration, clientOptions = {}) {
    this.socket = socket; this.registration = registration; this.actions = new Map(); this.inspectors = new Set(); this.titles = new Map(); this.loadedSettings = false; this.volumeDelta = 0; this.volumeTask = null;
    this.client = new Client({...clientOptions, onChange: () => this.render(), onSettings: value => {
      this.loadedSettings = true;
      this.send({event: 'setGlobalSettings', context: registration.uuid, payload: value});
    }});
  }
  send(value) { if (this.socket.readyState === 1) this.socket.send(JSON.stringify(value)); }
  start() { this.send(this.registration); this.send({event: 'getGlobalSettings', context: this.registration.uuid}); }
  info(context) {
    const state = this.client.snapshot;
    this.send({event: 'sendToPropertyInspector', context, payload: {options: this.client.options, status: this.client.status, detail: this.client.detail, busy: this.client.busy,
      track: state?.track ? `${clean(state.track.title, 200)} — ${clean(state.track.artists?.join(' · '), 200)}` : '',
      position: state ? `${Math.floor(state.playback.position || 0)} / ${Math.floor(state.playback.duration || 0)} seconds` : ''}});
  }
  render() {
    for (const [context, item] of this.actions) {
      const value = title(item.action, this.client);
      if (this.titles.get(context) !== value) { this.titles.set(context, value); this.send({event: 'setTitle', context, payload: {title: value, target: 0}}); }
      if (item.encoder) this.send({event: 'setFeedback', context, payload: {title: 'Volume', value: this.client.snapshot ? `${Math.round(this.client.snapshot.playback.volume)}%` : this.client.status, indicator: this.client.snapshot?.playback.volume || 0}});
    }
    for (const context of this.inspectors) this.info(context);
  }
  async adjustVolume(delta, context) {
    if (!Number.isFinite(delta) || !this.client.snapshot) { this.send({event: 'showAlert', context}); return; }
    this.volumeDelta = Math.max(-100, Math.min(100, this.volumeDelta + delta));
    if (this.volumeTask) return this.volumeTask;
    const generation = this.client.generation;
    this.volumeTask = (async () => {
      while (this.volumeDelta) {
        do {
          await this.client.commandDone;
          if (generation !== this.client.generation || !this.client.snapshot) throw new Error('Disconnected.');
        } while (this.client.busy);
        const delta = this.volumeDelta; this.volumeDelta = 0;
        const value = Math.max(0, Math.min(100, this.client.snapshot.playback.volume + delta));
        await this.client.command({command: 'volume', value});
      }
    })().catch(() => this.send({event: 'showAlert', context})).finally(() => {this.volumeDelta = 0; this.volumeTask = null;});
    return this.volumeTask;
  }
  async receive(message) {
    if (!message || typeof message !== 'object') return;
    const {event, context, action, payload = {}} = message;
    if (event === 'didReceiveGlobalSettings') {
      if (this.loadedSettings) return;
      this.loadedSettings = true;
      try {
        const value = settings({...DEFAULTS, ...payload.settings});
        await this.client.configure(value);
      } catch { this.client.publish('Settings invalid', 'Use a valid native executable and API port in the action settings.'); }
      return;
    }
    if (typeof action !== 'string' || !action.startsWith(UUID + '.') || !Object.hasOwn(ACTIONS, action.slice(UUID.length + 1)) || typeof context !== 'string' || context.length > 256) return;
    const name = action.slice(UUID.length + 1);
    if (event === 'willAppear') {
      if (this.actions.size >= 512 && !this.actions.has(context)) return;
      this.actions.set(context, {action: name, encoder: payload.controller === 'Encoder'});
      this.client.setActive(true); this.render(); return;
    }
    if (event === 'willDisappear') {
      this.actions.delete(context); this.titles.delete(context); this.inspectors.delete(context);
      this.client.setActive(this.actions.size > 0); return;
    }
    if (!this.actions.has(context)) return;
    if (event === 'propertyInspectorDidAppear') { this.inspectors.add(context); this.info(context); return; }
    if (event === 'propertyInspectorDidDisappear') { this.inspectors.delete(context); return; }
    if (event === 'sendToPlugin') {
      this.inspectors.add(context);
      if (payload.operation === 'pair') await this.client.pair(payload.code, payload.options);
      else if (payload.operation === 'forget') await this.client.forget();
      else if (payload.operation === 'reconnect' && !this.client.busy) await this.client.configure(this.client.options);
      this.info(context); return;
    }
    if (name === 'volume' && event === 'dialRotate') {
      await this.adjustVolume(Math.max(-50, Math.min(50, Number(payload.ticks))) * 2, context); return;
    }
    if (event === 'keyUp' && ['volume-up', 'volume-down'].includes(name)) {
      await this.adjustVolume(name === 'volume-up' ? 5 : -5, context); return;
    }
    if (event === 'keyUp' || name === 'volume' && ['dialUp', 'touchTap'].includes(event)) {
      try { await this.client.command(actionCommand(name, this.client.snapshot, event === 'dialRotate' ? payload.ticks : undefined)); }
      catch { this.send({event: 'showAlert', context}); }
    }
  }
  close() { this.client.close(); this.actions.clear(); this.inspectors.clear(); this.titles.clear(); }
}
export function main(args = process.argv.slice(2)) {
  const options = Object.fromEntries(Array.from({length: Math.floor(args.length / 2)}, (_, i) => [args[i * 2], args[i * 2 + 1]]));
  const port = Number(options['-port']);
  if (!Number.isInteger(port) || port < 1 || port > 65535 || options['-registerEvent'] !== 'registerPlugin' || !options['-pluginUUID']) return;
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  const plugin = new Plugin(socket, {event: 'registerPlugin', uuid: options['-pluginUUID']});
  socket.addEventListener('open', () => plugin.start());
  socket.addEventListener('message', event => {
    if (typeof event.data !== 'string' || event.data.length > 65536) return;
    try { plugin.receive(JSON.parse(event.data)).catch(() => {}); } catch {}
  });
  socket.addEventListener('close', () => plugin.close());
  socket.addEventListener('error', () => { plugin.close(); socket.close(); });
  process.once('SIGTERM', () => { plugin.close(); socket.close(); });
  process.once('SIGINT', () => { plugin.close(); socket.close(); });
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
