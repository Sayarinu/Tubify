"use strict";
(() => {
  const params = new URLSearchParams(location.search);
  const layouts = ["full", "compact", "text", "badge", "poster", "ticker", "display"];
  const layout = layouts.includes(params.get("layout")) ? params.get("layout") : "full";
  const enabled = name => !["0", "false", "off"].includes(params.get(name));
  const scale = Math.max(.25, Math.min(4, Number(params.get("scale")) || 1));
  document.body.classList.add(layout);
  if (enabled("transparent")) document.body.classList.add("transparent");
  document.documentElement.style.setProperty("--scale", scale);
  const el = name => document.getElementById(name);
  for (const name of ["artwork", "title", "artist", "progress"]) el(name).hidden = !enabled(name === "artwork" ? "art" : name);
  const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
  const preview = params.get("preview") === "1";
  let snapshot = null, received = 0, revision = 0, artKey = "", objectUrl = "", generation = 0, stopped = false;
  let artRequest = null;
  const time = value => `${Math.floor(Math.max(0,value)/60)}:${String(Math.floor(Math.max(0,value)%60)).padStart(2,"0")}`;
  const finite = value => Number.isFinite(value) ? Math.max(0,value) : 0;
  function clearArtwork() {
    if (artRequest) artRequest.abort();
    artRequest = null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = "";
    el("cover").removeAttribute("src");
    el("artwork").classList.remove("has-image");
  }
  function clear(message) {
    generation++;
    artKey = "";
    snapshot = null;
    clearArtwork();
    el("card").hidden = true;
    el("notice").textContent = message;
  }
  async function request(path, signal) {
    const response = await fetch(path, {headers: {Authorization: `Bearer ${token}`}, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer", mode: "same-origin", signal: signal || AbortSignal.timeout(25000)});
    if (response.status === 401 || response.status === 403) {
      stopped = true;
      throw new Error("pairing");
    }
    if (!response.ok) throw new Error("unavailable");
    return response;
  }
  async function artwork(path, current) {
    clearArtwork();
    if (!enabled("art") || !/^\/v1\/artwork\/[A-Za-z0-9_-]+$/.test(path)) return;
    const controller = new AbortController();
    artRequest = controller;
    const deadline = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await request(path, controller.signal);
      const blob = await response.blob();
      if (current !== generation || blob.size > 8 * 1024 * 1024 || !["image/png", "image/jpeg", "image/webp", "image/gif"].includes(blob.type)) return;
      objectUrl = URL.createObjectURL(blob);
      el("cover").src = objectUrl;
      el("artwork").classList.add("has-image");
    } catch (_) {
      if (stopped) clear("Overlay access was revoked. Generate a new source URL in the app.");
      else if (current === generation) artKey = ""; // Retry the current cover on the next snapshot.
    } finally {
      clearTimeout(deadline);
      if (artRequest === controller) artRequest = null;
    }
  }
  function progress() {
    if (!snapshot) return;
    const play = snapshot.playback || {};
    const duration = finite(play.duration);
    const position = Math.min(duration, finite(play.position) + (play.state === "playing" ? (performance.now() - received) / 1000 : 0));
    el("fill").style.width = `${duration ? position / duration * 100 : 0}%`;
    el("elapsed").textContent = time(position);
    el("duration").textContent = time(duration);
  }
  function render(value) {
    if (!value || typeof value !== "object" || !value.playback) throw new Error("invalid");
    const track = value.track;
    if (!track || !track.title) { clear("Nothing playing"); return; }
    if (value.playback.state !== "playing" && params.get("paused") === "hide") { clear(""); return; }
    snapshot = value;
    received = performance.now();
    el("card").hidden = false;
    el("notice").textContent = "";
    el("title").textContent = String(track.title).slice(0,512);
    el("artist").textContent = Array.isArray(track.artists) ? track.artists.filter(v => typeof v === "string").join(" · ").slice(0,512) : "";
    el("state").textContent = value.playback.state === "playing" ? "NOW PLAYING" : "PAUSED";
    el("ticker").style.setProperty("--ticker-width", `${el("ticker").parentElement.clientWidth}px`);
    const path = typeof track.artwork === "string" ? track.artwork : "";
    if (path !== artKey) { artKey = path; artwork(path, ++generation); }
    progress();
  }
  async function listen() {
    while (!stopped) {
      try {
        const path = revision ? `/v1/events?after=${revision}&timeout=20` : "/v1/state";
        const value = await (await request(path)).json();
        render(value);
        revision = Math.max(1, Math.floor(finite(value.revision)));
      } catch (_) {
        clear(stopped ? "Overlay access was revoked. Generate a new source URL in the app." : "Waiting for Tubify…");
        revision = 0;
        if (!stopped) await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
  }
  setInterval(progress, 250);
  addEventListener("pagehide", () => { stopped = true; clearArtwork(); });
  if (preview) {
    el("preview").hidden = false;
    render({revision:1,playback:{state:"playing",position:42,duration:204},track:{title:"After the rain",artists:["The Sunday Letters"],artwork:""}});
  } else if (!token) {
    clear("Generate a read-only OBS source URL in Tubify settings.");
  } else {
    listen();
  }
})();
