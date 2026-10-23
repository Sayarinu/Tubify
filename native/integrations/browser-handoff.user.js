// ==UserScript==
// @name         YouTube Music Native handoff
// @namespace    com.carter.youtube-music.native
// @version      1.0.0
// @description  Explicitly open, play or queue music in Tubify, enabled per host.
// @match        https://music.youtube.com/*
// @match        https://www.youtube.com/*
// @match        https://youtube.com/*
// @match        https://m.youtube.com/*
// @match        https://youtu.be/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @run-at       document-idle
// ==/UserScript==

(() => {
    "use strict";
    const host = location.hostname;
    const preference = "enabled:" + host;
    let enabled = GM_getValue(preference, false);
    let panel;
    const valid = () => {
        const url = new URL(location.href);
        if (url.hostname === "youtu.be") return /^\/[A-Za-z0-9_-]{11}$/.test(url.pathname);
        if (url.pathname === "/watch") return url.searchParams.getAll("v").length === 1 && /^[A-Za-z0-9_-]{11}$/.test(url.searchParams.get("v") || "");
        if (url.pathname === "/playlist") return url.searchParams.getAll("list").length === 1 && /^[A-Za-z0-9_-]{2,200}$/.test(url.searchParams.get("list") || "");
        return /^\/(?:channel|browse)\/UC[A-Za-z0-9_-]{22}$/.test(url.pathname) || /^\/browse\/MPRE[A-Za-z0-9_-]{1,196}$/.test(url.pathname);
    };
    function render() {
        if (panel) panel.remove();
        panel = null;
        if (!enabled || !valid()) return;
        panel = document.createElement("div");
        panel.setAttribute("role", "group");
        panel.setAttribute("aria-label", "Tubify handoff");
        Object.assign(panel.style, { position: "fixed", bottom: "100px", right: "16px", zIndex: "2147483647", display: "flex", gap: "8px", padding: "8px", borderRadius: "12px", background: "#212121", color: "#fff", boxShadow: "0 2px 12px #0008", font: "14px system-ui" });
        for (const [action, label] of [["open", "Open in Tubify"], ["play", "Play"], ["queue", "Queue"]]) {
            if (action !== "open" && /^\/(?:channel|browse)\/UC/.test(location.pathname)) continue;
            const link = document.createElement("a");
            link.textContent = label;
            link.href = "ytmusic-native://" + action + "?url=" + encodeURIComponent(location.origin + location.pathname + location.search);
            Object.assign(link.style, { color: "#fff", background: "#363636", borderRadius: "8px", padding: "8px", textDecoration: "none" });
            panel.append(link);
        }
        const dismiss = document.createElement("button");
        dismiss.textContent = "×";
        dismiss.setAttribute("aria-label", "Hide Tubify handoff for this page");
        dismiss.addEventListener("click", () => { panel.remove(); panel = null; });
        panel.append(dismiss);
        document.documentElement.append(panel);
    }
    GM_registerMenuCommand("Toggle Tubify handoff on " + host, () => {
        enabled = !enabled;
        GM_setValue(preference, enabled);
        render();
    });
    // YouTube announces client-side navigation without reloading userscripts.
    document.addEventListener("yt-navigate-finish", render);
    window.addEventListener("popstate", render);
    render();
})();
