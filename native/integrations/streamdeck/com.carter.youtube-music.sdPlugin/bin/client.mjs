import http from 'node:http';
import {execFile} from 'node:child_process';

export const DEFAULTS = Object.freeze({port: 9864, executable: 'youtube-music-native', autoConnect: false});
export function settings(value = {}) {
  const port = Number(value.port);
  const executable = typeof value.executable === 'string' ? value.executable.trim() : DEFAULTS.executable;
  if (!Number.isInteger(port) || port < 1024 || port > 65535 || !executable || executable.length > 4096 || /[\x00-\x1f]/.test(executable)) throw new Error('Use an API port from 1024 to 65535 and the Tubify executable.');
  return {port, executable, autoConnect: value.autoConnect === true};
}
export function validCredential(value, port) {
  return value && value.port === port && value.scope === 'control' && /^[a-f0-9]{32}$/.test(value.clientId) && /^[A-Za-z0-9_-]{43}$/.test(value.token);
}
export function vault(executable, request) {
  return new Promise((resolve, reject) => {
    const child = execFile(executable, ['--streamdeck-credentials'], {shell: false, windowsHide: true, timeout: 15000, maxBuffer: 8192, encoding: 'utf8'}, (error, output) => {
      try {
        const result = JSON.parse(output);
        if (error || !result.ok) throw new Error();
        resolve(result.credential ?? null);
      } catch { reject(new Error('System keyring unavailable. Check the native executable path and unlock the keyring.')); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(request));
  });
}
export function request(port, path, {token, body, signal, timeout = 8000} = {}) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
    // http.request connects directly to a literal loopback address; no proxies or redirects.
    const req = http.request({hostname: '127.0.0.1', port, path, method: data ? 'POST' : 'GET', signal, agent: false,
      headers: {...(token ? {Authorization: 'Bearer ' + token} : {}), ...(data ? {'Content-Type': 'application/json', 'Content-Length': data.length} : {})}}, response => {
      let size = 0; const chunks = [];
      response.on('data', chunk => {
        size += chunk.length;
        if (size > 65536) req.destroy(new Error('Response too large.'));
        else chunks.push(chunk);
      });
      response.on('error', reject);
      response.on('end', () => {
        if (response.statusCode < 200 || response.statusCode >= 300) {
          const error = new Error(response.statusCode === 401 || response.statusCode === 403 ? 'Pair a new playback-control client in Tubify.' : 'Tubify unavailable. Check the app before retrying.');
          error.status = response.statusCode; reject(error); return;
        }
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
        catch { reject(new Error('Tubify returned an invalid response.')); }
      });
    });
    const deadline = setTimeout(() => req.destroy(new Error('Tubify request timed out.')), timeout);
    req.on('close', () => clearTimeout(deadline));
    req.on('error', reject);
    req.end(data);
  });
}

export class Client {
  constructor({onChange = () => {}, onSettings = () => {}, storage = vault, send = request, schedule = setTimeout, cancel = clearTimeout} = {}) {
    Object.assign(this, {onChange, onSettings, storage, send, schedule, cancel});
    this.options = {...DEFAULTS}; this.credential = null; this.snapshot = null;
    this.status = 'Pair in settings'; this.detail = 'Enable Local API in Tubify and create a playback-control pairing code.';
    this.generation = 0; this.active = false; this.busy = false; this.attempts = 0; this.timer = null;
    this.controller = new AbortController(); this.commandDone = Promise.resolve();
  }
  publish(status, detail = '') { this.status = status; this.detail = detail; this.onChange(); }
  stop() { this.generation++; this.cancel(this.timer); this.timer = null; this.controller.abort(); this.controller = new AbortController(); this.snapshot = null; }
  close() { this.active = false; this.stop(); this.credential = null; }
  setActive(active) {
    if (active === this.active) return;
    this.active = active;
    if (!active) this.stop();
    else if (this.credential) this.poll();
  }
  async configure(value) {
    this.stop(); this.credential = null; const generation = this.generation;
    this.options = settings({...DEFAULTS, ...value});
    if (!this.options.autoConnect) { this.publish('Pair in settings'); return; }
    try {
      const saved = await this.storage(this.options.executable, {action: 'read'});
      if (generation !== this.generation) return;
      if (!validCredential(saved, this.options.port)) { this.publish('Pair in settings', 'No matching playback-control credential is saved for this port.'); return; }
      this.credential = saved; this.attempts = 0;
      if (this.active) this.poll();
    } catch (error) { if (generation === this.generation) this.publish('Keyring unavailable', error.message); }
  }
  async pair(code, value) {
    if (this.busy) return;
    this.busy = true; this.stop(); this.credential = null;
    const generation = this.generation;
    let created = false;
    try {
      this.options = settings({...DEFAULTS, ...value, autoConnect: false});
      this.onSettings(this.options);
      if (typeof code !== 'string' || !/^[A-Za-z0-9_-]{16,128}$/.test(code)) throw new Error('Enter the current pairing code from Tubify.');
      this.publish('Pairing');
      const result = await this.send(this.options.port, '/v1/pair', {body: {code}, signal: this.controller.signal});
      if (generation !== this.generation) return;
      created = true;
      const credential = {...result, port: this.options.port};
      if (!validCredential(credential, this.options.port)) throw new Error('Create a playback-control code, not a read-only overlay code.');
      await this.storage(this.options.executable, {action: 'write', credential});
      if (generation !== this.generation) return;
      this.credential = credential; this.options.autoConnect = true; this.attempts = 0;
      this.onSettings(this.options); this.publish('Connecting');
      if (this.active) this.poll();
    } catch (error) {
      if (generation === this.generation) this.publish('Pairing failed', error.message + (created ? ' Revoke the newly created client in Tubify before trying again.' : ''));
    } finally { this.busy = false; }
  }
  async forget() {
    if (this.busy) return;
    this.busy = true; this.stop(); this.credential = null;
    this.options.autoConnect = false; this.onSettings(this.options);
    try {
      await this.storage(this.options.executable, {action: 'delete'});
      this.publish('Pair in settings', 'Saved connection removed. Revoke this client in Tubify to invalidate its token.');
    } catch (error) { this.publish('Disconnected', error.message + ' Automatic connection is disabled. Revoke the client in Tubify.'); }
    finally { this.busy = false; }
  }
  acceptSnapshot(value, expectedInstance = this.snapshot?.instanceId) {
    const p = value?.playback, c = value?.capabilities;
    if (value?.instanceId !== undefined && (typeof value.instanceId !== 'string' || !/^[a-f0-9]{32}$/.test(value.instanceId))) throw new Error('Unsupported local API instance.');
    if (value?.version !== 1 || !Number.isSafeInteger(value.revision) || value.revision < 0 || !p || !c ||
        !['playing', 'paused', 'stopped'].includes(p.state) || !['off', 'one', 'all'].includes(p.repeat) || typeof p.shuffle !== 'boolean' ||
        ![p.position, p.duration, p.volume].every(number => Number.isFinite(number) && number >= 0) || p.volume > 100 ||
        !['play', 'seek', 'next', 'previous', 'rate'].every(key => typeof c[key] === 'boolean') ||
        value.track !== null && (!value.track || typeof value.track.title !== 'string' || !Array.isArray(value.track.artists) || !value.track.artists.every(name => typeof name === 'string'))) throw new Error('Unsupported local API state.');
    if (this.snapshot) {
      if (value.instanceId === this.snapshot.instanceId && value.revision < this.snapshot.revision) return false;
      // A command may already have observed a restart while this poll was in flight.
      if (value.instanceId !== this.snapshot.instanceId && this.snapshot.instanceId !== expectedInstance) return false;
    }
    this.snapshot = value;
    return true;
  }
  async poll() {
    if (!this.active || !this.credential) return;
    const generation = this.generation;
    const revision = this.snapshot?.revision, instance = this.snapshot?.instanceId;
    try {
      const result = await this.send(this.options.port, revision === undefined ? '/v1/state' : `/v1/events?after=${revision}&timeout=20`, {token: this.credential.token, signal: this.controller.signal, timeout: 25000});
      if (generation !== this.generation) return;
      this.acceptSnapshot(result, instance); this.attempts = 0; this.publish('Connected');
      this.timer = this.schedule(() => this.poll(), 100);
    } catch (error) {
      if (generation !== this.generation) return;
      this.snapshot = null;
      if (error.status === 401 || error.status === 403) {
        this.unauthorized();
      } else {
        this.publish('Offline', 'Open Tubify and enable Local API. Reconnecting automatically.');
        this.timer = this.schedule(() => this.poll(), Math.min(30000, 1000 * 2 ** Math.min(5, this.attempts++)));
      }
    }
  }
  unauthorized() {
    this.stop(); this.credential = null; this.options.autoConnect = false; this.onSettings(this.options);
    this.publish('Pair again', 'Access was revoked or lacks playback-control permission. Create a new code in Tubify.');
  }
  async command(command) {
    if (!this.credential || !this.snapshot || this.busy) throw new Error('Wait for a connected native player before using controls.');
    this.busy = true; const generation = this.generation;
    let release; this.commandDone = new Promise(resolve => { release = resolve; });
    try {
      await this.send(this.options.port, '/v1/command', {token: this.credential.token, body: command, signal: this.controller.signal});
      // Refresh absolute volume/shuffle values before accepting another action.
      const instance = this.snapshot?.instanceId;
      const state = await this.send(this.options.port, '/v1/state', {token: this.credential.token, signal: this.controller.signal});
      if (generation === this.generation) { this.acceptSnapshot(state, instance); this.onChange(); }
    } catch (error) {
      if (generation === this.generation) {
        if (error.status === 401 || error.status === 403) this.unauthorized();
        else { this.snapshot = null; this.publish('Check Tubify', 'The command was not confirmed. Check playback before retrying; commands are never replayed automatically.'); }
      }
      throw new Error('Command not confirmed.');
    } finally { this.busy = false; release(); }
  }
}
