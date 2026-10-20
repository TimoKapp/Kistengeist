"use strict";
// Setup-Assistent von Kistengeist (ohne externe Bibliotheken).

const PAGES = ["welcome", "legal", "usb", "mode", "modules", "internet", "account", "summary", "progress", "done"];
const MODE_LABEL = { desktop: "Nur Bildschirm", rdp: "Nur Fernzugriff", both: "Beides" };
const REMOTE_LABEL = { browser: "Browser (https://kistengeist.local:8443)", rdp: "Remotedesktop (RDP)" };

function remote() {
  const r = document.querySelector("input[name=remote]:checked");
  return r ? r.value : "browser";
}

function renderRemoteChoice() {
  $("remote-choice").hidden = mode() === "desktop";
}

const $ = (id) => document.getElementById(id);
let info = null;
let current = "welcome";
const selection = new Set(); // vom Nutzer gewählte, nicht verpflichtende Module
let lastPayload = null;
let pollTimer = null;
let statusMode = "";
let statusRemote = "";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

// Einrichtungscode: steht am Bildschirm des Pi (QR-Code enthält ihn), im Windows-Werkzeug bzw. am
// Ende von install.sh. Ohne ihn liefert der Pi außer der Grundinfo nichts aus.
let setupCode = "";
try { setupCode = sessionStorage.getItem("kg-code") || ""; } catch (e) { /* privates Fenster */ }

async function api(path, body) {
  const headers = { "X-Setup-Code": setupCode };
  const options = body === undefined ? { headers } : {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, options);
  let data = {};
  try { data = await res.json(); } catch (e) { /* leer */ }
  if (!res.ok) throw new Error(data.error || `Fehler ${res.status}`);
  return data;
}

function show(page) {
  current = page;
  for (const p of PAGES) $(`page-${p}`).hidden = p !== page;
  const steps = $("steps");
  steps.replaceChildren(...PAGES.map((p, i) => el("li", {
    class: i < PAGES.indexOf(page) ? "done" : (p === page ? "current" : ""),
    title: p,
  })));
  window.scrollTo(0, 0);
}

function mode() {
  return document.querySelector("input[name=mode]:checked").value;
}

function modulesById() {
  return Object.fromEntries(info.modules.map((m) => [m.id, m]));
}

// ------------------------------------------------------------ Netzwerk

function renderNetwork() {
  const net = info.network;
  const status = $("net-status");
  if (net.online) {
    status.className = "ok";
    status.textContent = `Online – erreichbar unter http://${net.hostname}.local` +
      (net.ips.length ? ` oder http://${net.ips[0]}` : "");
  } else {
    status.className = "error";
    status.textContent = net.hotspot
      ? "Kein Internet. Du bist mit dem Einrichtungs-WLAN „Kistengeist-Setup“ verbunden."
      : "Kein Internet. Bitte ein Netzwerkkabel anschließen oder WLAN wählen.";
  }
  const form = $("wifi-form");
  form.hidden = net.online;
  const select = $("wifi-ssid");
  const chosen = select.value;
  select.replaceChildren(el("option", { value: "", text: "– bitte wählen –" }),
    ...net.wifi.map((w) => el("option", { value: w.ssid, text: `${w.ssid} (${w.signal} %)` })));
  select.value = chosen;
  $("welcome-next").disabled = !net.online;
}

async function connectWifi() {
  const ssid = $("wifi-ssid-manual").value.trim() || $("wifi-ssid").value;
  try {
    await api("/api/wifi", { ssid, password: $("wifi-password").value });
    $("wifi-hint").textContent =
      `Der Pi verbindet sich mit „${ssid}“. Verbinde dein Gerät wieder mit deinem WLAN und öffne ` +
      `http://${info.network.hostname}.local (oder die IP-Adresse, die am Bildschirm des Pi steht).`;
  } catch (e) {
    $("wifi-hint").textContent = e.message;
  }
}

// ------------------------------------------------------------ Rechtliches

function renderLegal() {
  const legal = info.legal;
  $("legal-title").textContent = legal.title;
  // Absätze kommen als vom Server erzeugtes, bereits escaptes HTML (nur Fettdruck und https-Links).
  $("legal-intro").innerHTML = legal.intro;
  const box = $("legal-text");
  box.replaceChildren();
  for (const sec of legal.sections) {
    box.append(el("h2", { text: sec.title }));
    for (const html of sec.paragraphs) {
      const p = document.createElement("p");
      p.innerHTML = html;
      box.append(p);
    }
  }
  $("legal-checks").replaceChildren(...legal.confirmations.map((c) => {
    const input = el("input", { type: "checkbox", "data-legal": c.id });
    input.addEventListener("change", updateLegalButton);
    return el("label", { class: "check" }, input, el("span", { text: c.text }));
  }));
  $("legal-version").textContent = `Stand ${legal.updated} · Version ${legal.version}`;
  updateLegalButton();
}

function legalAnswer() {
  const checks = {};
  for (const box of document.querySelectorAll("[data-legal]")) checks[box.dataset.legal] = box.checked;
  return { version: info.legal.version, checks };
}

function updateLegalButton() {
  $("legal-next").disabled = !Object.values(legalAnswer().checks).every(Boolean);
}

// ------------------------------------------------------------ USB-Stick

let sticks = [];

async function loadUsb() {
  $("usb-error").textContent = "";
  try {
    sticks = (await api("/api/usb")).sticks;
  } catch (e) {
    $("usb-error").textContent = e.message;
    sticks = [];
  }
  renderUsb();
}

function chosenStick() {
  const r = document.querySelector("input[name=usb]:checked");
  return r ? r.value : null; // "" = ohne Stick
}

function renderUsb() {
  const before = chosenStick();
  const items = sticks.map((s) => el("label", { class: "stick" },
    el("input", { type: "radio", name: "usb", value: s.id, checked: before === s.id || (before === null && sticks.length === 1) }),
    el("strong", { text: `${s.name} · ${s.sizeText}` }),
    el("span", { text: `${s.device} – Inhalt: ${s.content}` })));
  items.push(el("label", { class: "stick" },
    el("input", { type: "radio", name: "usb", value: "", checked: before === "" }),
    el("strong", { text: "Ohne USB-Stick fortfahren" }),
    el("span", { text: "Nicht empfohlen: Sicherungen und Austausch per Stick fehlen dann." })));
  $("usb-list").replaceChildren(
    sticks.length ? el("p", { text: "Gefundene USB-Sticks:" })
      : el("p", { class: "error", text: "Kein USB-Stick gefunden. Bitte einstecken und „Erneut suchen“ drücken." }),
    ...items);
  for (const r of document.querySelectorAll("input[name=usb]")) r.addEventListener("change", () => {
    $("usb-confirm").checked = false; // Löschbestätigung gilt nur für den Stick, für den sie gegeben wurde
    updateUsbOptions();
  });
  if (chosenStick() !== before) $("usb-confirm").checked = false;
  updateUsbOptions();
}

function updateUsbOptions() {
  const id = chosenStick();
  const stick = sticks.find((s) => s.id === id);
  $("usb-options").hidden = !stick;
  if (stick && !stick.usable) $("usb-format").checked = true;
  $("usb-format").disabled = !!stick && !stick.usable;
  $("usb-confirm-row").hidden = !$("usb-format").checked;
}

function stickText(id) {
  const s = sticks.find((x) => x.id === id);
  return s ? `${s.name}, ${s.sizeText}, ${s.device} (Inhalt: ${s.content})` : id;
}

function usbPayload() {
  const id = chosenStick() || "";
  return {
    device: id,
    format: !!id && $("usb-format").checked,
    formatConfirmed: $("usb-confirm").checked,
    label: $("usb-label").value.trim() || "KISTENGEIST",
  };
}

function usbValid() {
  const u = usbPayload();
  if (chosenStick() === null) return "Bitte einen USB-Stick wählen (oder „Ohne USB-Stick fortfahren“).";
  if (u.device && !/^[A-Za-z0-9_-]{1,11}$/.test(u.label)) return "Bezeichnung: 1–11 Zeichen, nur Buchstaben, Ziffern, - und _.";
  if (u.format && !u.formatConfirmed) return "Bitte bestätigen, dass alle Daten auf dem Stick gelöscht werden.";
  return "";
}

// ------------------------------------------------------------ Module

function dependentsOf(id, byId) {
  return info.modules.filter((m) => m.depends.includes(id)).map((m) => m.id)
    .filter((d) => byId[d]);
}

function setChecked(id, on, byId) {
  const mod = byId[id];
  if (!mod || mod.required) return;
  if (on) {
    selection.add(id);
    for (const dep of mod.depends) setChecked(dep, true, byId);
  } else {
    selection.delete(id);
    for (const child of dependentsOf(id, byId)) setChecked(child, false, byId);
  }
}

function renderModules() {
  const m = mode();
  const byId = modulesById();
  const visible = info.modules.filter((mod) => mod.modes.includes(m));
  const groups = [...new Set(visible.map((mod) => mod.group))];
  const list = $("module-list");
  list.replaceChildren(...groups.map((group) => el("div", { class: "group" },
    el("h2", { text: group }),
    ...visible.filter((mod) => mod.group === group).map((mod) => {
      const input = el("input", {
        type: "checkbox",
        checked: mod.required || selection.has(mod.id),
        disabled: mod.required,
        "data-id": mod.id,
      });
      input.addEventListener("change", () => {
        setChecked(mod.id, input.checked, byId);
        renderModules();
      });
      const deps = mod.depends.filter((d) => byId[d] && !byId[d].required).map((d) => byId[d].name);
      return el("label", { class: "module" + (mod.required ? " locked" : "") }, input,
        el("strong", { text: mod.name + (mod.required ? " (erforderlich)" : "") }),
        el("span", { class: "desc", text: mod.description + (deps.length ? ` Braucht: ${deps.join(", ")}.` : "") }),
        mod.note ? el("span", { class: "note", text: mod.note }) : null);
    }))));
}

// ------------------------------------------------------------ Internet und n8n

function planHas(id) {
  const byId = modulesById();
  return selection.has(id) && byId[id] && byId[id].modes.includes(mode());
}

function needsInternet() {
  return planHas("webserver") || planHas("n8n");
}

function netChoice() {
  const r = document.querySelector("input[name=net]:checked");
  return r ? r.value : "lan";
}

function renderInternet() {
  $("inet-web").hidden = !planHas("webserver");
  $("inet-n8n").hidden = !planHas("n8n");
  const net = netChoice();
  $("guide-dyndns").hidden = net !== "dyndns";
  const prov = ddnsProvider();
  for (const id of ["ipv64", "dynv6", "noip", "duckdns"]) $("guide-" + id).hidden = id !== prov;
  $("ddns-host").placeholder = DDNS_EXAMPLE[prov];
  $("ddns-token-row").hidden = prov === "noip";
  $("ddns-key-rows").hidden = prov !== "noip";
  $("guide-tailscale").hidden = net !== "tailscale";
  $("file-usb").disabled = !planHas("usb-stick");
  if (!planHas("usb-stick")) $("file-usb").checked = false;
}

const DDNS_LABEL = { ipv64: "ipv64.net", dynv6: "dynv6", noip: "No-IP", duckdns: "DuckDNS" };
// Gegenstück zu kistengeist_ddns.PROVIDERS (No-IP: viele Gratis-Domains, daher ohne Liste).
const DDNS_DOMAINS = {
  ipv64: ["ipv64.net", "ipv64.de", "any64.de", "api64.de", "dns64.de", "dyndns64.de", "dynipv6.de", "eth64.de",
    "home64.de", "iot64.de", "lan64.de", "nas64.de", "root64.de", "route64.de", "srv64.de", "tcp64.de", "udp64.de",
    "vpn64.de", "wan64.de"],
  dynv6: ["dynv6.net", "dns.army", "dns.navy", "v6.army", "v6.navy", "v6.rocks"],
  noip: [],
  duckdns: ["duckdns.org"],
};
const DDNS_EXAMPLE = { ipv64: "meinpi.ipv64.net", dynv6: "meinpi.dynv6.net", noip: "meinpi.ddns.net",
  duckdns: "meinpi.duckdns.org" };

function ddnsProvider() {
  const r = document.querySelector("input[name=ddns]:checked");
  return r ? r.value : "ipv64";
}

function ddnsHost(v) {
  let h = v.trim().toLowerCase().replace(/^[a-z]+:\/\//, "").split("/")[0].replace(/^\.+|\.+$/g, "");
  if (ddnsProvider() === "duckdns" && h && !h.includes(".")) h += ".duckdns.org";
  return h;
}

function ddnsPayload() {
  return {
    provider: ddnsProvider(),
    host: ddnsHost($("ddns-host").value),
    token: $("ddns-token").value.trim(),
    user: $("ddns-user").value.trim(),
    password: $("ddns-pass").value,
    ipv6Only: $("ddns-v6").checked,
  };
}

function internetPayload() {
  return {
    net: netChoice(),
    ...ddnsPayload(),
    acmeEmail: $("acme-email").value.trim(),
    tailscaleKey: $("ts-key").value.trim(),
    n8n: planHas("n8n") ? {
      firstName: $("n8n-first").value.trim(),
      lastName: $("n8n-last").value.trim(),
      email: $("n8n-email").value.trim(),
      password: $("n8n-pw1").value,
      license: $("n8n-license").value.trim(),
    } : null,
    fileSecrets: $("file-secrets").checked,
    fileUsb: $("file-usb").checked,
  };
}

function internetValid() {
  const p = internetPayload();
  if (planHas("webserver") && p.net === "dyndns") {
    if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?){2,}$/.test(p.host))
      return `Bitte deine komplette Adresse eingeben, z. B. ${DDNS_EXAMPLE[p.provider]}.`;
    const doms = DDNS_DOMAINS[p.provider];
    if (doms.length && !doms.includes(p.host.split(".").slice(1).join(".")))
      return `Die Adresse muss auf eine Domain von ${DDNS_LABEL[p.provider]} enden, z. B. ${DDNS_EXAMPLE[p.provider]}.`;
    if (p.provider === "noip") {
      if (!p.user || !p.password) return "Bitte Benutzername und Passwort des DDNS-Keys von No-IP einfügen.";
    } else if (p.provider === "duckdns" ? !/^[0-9a-f-]{36}$/i.test(p.token) : !/^[A-Za-z0-9_.-]{8,200}$/.test(p.token)) {
      return `Bitte den Token von ${DDNS_LABEL[p.provider]} vollständig einfügen.`;
    }
  }
  if (planHas("webserver") && p.net === "tailscale" && p.tailscaleKey && !p.tailscaleKey.startsWith("tskey-"))
    return "Der Tailscale-Schlüssel beginnt mit „tskey-“.";
  if (p.n8n) {
    if (!p.n8n.firstName || !p.n8n.lastName) return "Bitte Vor- und Nachnamen für n8n angeben.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(p.n8n.email)) return "Bitte eine gültige E-Mail für n8n angeben.";
    const pw = p.n8n.password;
    if (pw.length < 8 || pw.length > 64 || !/\d/.test(pw) || !/[A-ZÄÖÜ]/.test(pw))
      return "n8n-Passwort: 8–64 Zeichen, mindestens eine Ziffer und ein Großbuchstabe.";
    if (pw !== $("n8n-pw2").value) return "Die n8n-Passwörter stimmen nicht überein.";
  }
  return "";
}

async function testDdns() {
  $("ddns-result").textContent = "Prüfe …";
  $("ddns-result").className = "hint";
  try {
    const r = await api("/api/ddns-test", ddnsPayload());
    $("ddns-result").textContent = r.ok
      ? `OK – ${r.host} zeigt jetzt auf deinen Internetanschluss${r.ip ? " (" + r.ip + ")" : ""}.`
      : (r.detail || "Prüfung fehlgeschlagen.");
    $("ddns-result").className = r.ok ? "ok" : "error";
  } catch (e) {
    $("ddns-result").textContent = e.message;
    $("ddns-result").className = "error";
  }
}

// ------------------------------------------------------------ Konto

function fillSelect(id, values, chosen) {
  const entries = Array.isArray(values) ? values.map((v) => [v, v]) : Object.entries(values);
  $(id).replaceChildren(...entries.map(([value, label]) =>
    el("option", { value, text: label, selected: value === chosen })));
}

function renderAccount() {
  const m = mode();
  // Bei "beides" ist die automatische Anmeldung nötig, sonst gibt es nichts zu spiegeln.
  $("autologin-row").hidden = m !== "desktop";
  $("pw-note").textContent = m === "both" && remote() === "rdp"
    ? "Hinweis: Bei der RDP-Spiegelung zählen nur die ersten 8 Zeichen – wähle sie nicht zu einfach. " +
      "Am Pi meldet sich Kistengeist automatisch an."
    : `Mindestens ${info.minPassword} Zeichen.`;
  $("browser-pw-row").hidden = !(m !== "desktop" && remote() === "browser");
}

function accountValid() {
  const pw = $("pw1").value;
  if (pw.length < info.minPassword) return `Das Passwort braucht mindestens ${info.minPassword} Zeichen.`;
  if (pw !== $("pw2").value) return "Die Passwörter stimmen nicht überein.";
  if (!$("browser-pw-row").hidden) {
    const b = $("bpw1").value;
    if (b.length < info.minPassword) return `Das Browser-Passwort braucht mindestens ${info.minPassword} Zeichen.`;
    if (b !== $("bpw2").value) return "Die Browser-Passwörter stimmen nicht überein.";
    if (b === pw) return "Bitte für den Browser ein anderes Passwort als das Anmeldepasswort wählen.";
  }
  return "";
}

// ------------------------------------------------------------ Zusammenfassung

function payload() {
  const m = mode();
  const byId = modulesById();
  return {
    mode: m,
    remote: remote(),
    modules: [...selection].filter((id) => byId[id] && byId[id].modes.includes(m)),
    password: $("pw1").value,
    browserPassword: m !== "desktop" && remote() === "browser" ? $("bpw1").value : "",
    autologin: m === "both" || (m === "desktop" && $("autologin").checked) || (m === "rdp" && remote() === "browser"),
    locale: $("locale").value,
    keymap: $("keymap").value,
    timezone: $("timezone").value,
    privacy_minimal: $("privacy-minimal").checked,
    legal: legalAnswer(),
    usb: usbPayload(),
    internet: internetPayload(),
    clientTime: Date.now(), // Pi ohne Echtzeituhr: Zeit des Browsers als Rückfall
  };
}

function renderSummary() {
  const p = payload();
  const names = info.modules
    .filter((mod) => mod.modes.includes(p.mode) && (mod.required || p.modules.includes(mod.id)))
    .map((mod) => mod.name);
  const rows = [
    ["Zugangsart", MODE_LABEL[p.mode] + (p.mode === "desktop" ? "" : ` – ${REMOTE_LABEL[p.remote]}`)],
    ["Module", names.join(", ")],
    ["Benutzer", info.user],
    ["Automatische Anmeldung", p.mode === "rdp" ? (p.remote === "browser" ? "ja (Sitzung läuft im Hintergrund)" : "–")
      : (p.autologin ? "ja" : "nein")],
    ["Sprache / Tastatur", `${info.locales[p.locale]} / ${info.keymaps[p.keymap]}`],
    ["Zeitzone", p.timezone],
    ["Datensparsam", p.privacy_minimal ? "ja" : "nein"],
    ["USB-Stick", p.usb.device ? stickText(p.usb.device) +
      (p.usb.format ? ` – wird mit exFAT formatiert („${p.usb.label}“), alle Daten werden gelöscht` : " – wird ohne Formatieren eingebunden")
      : "keiner"],
  ];
  if (planHas("webserver")) {
    const ip = p.internet;
    rows.push(["Erreichbarkeit", ip.net === "dyndns" ? `https://${ip.host} über ${DDNS_LABEL[ip.provider]} (Ports 80/443 am Router freigeben)`
      : ip.net === "tailscale" ? "Tailscale Funnel (ohne Portfreigabe)" : "nur im Heimnetz"]);
  }
  if (p.internet.n8n) rows.push(["n8n-Konto", p.internet.n8n.email]);
  rows.push(["Zugangsdaten-Datei", "~/Zugangsdaten.txt" + (p.internet.fileSecrets ? " mit Passwörtern" : " ohne Passwörter") +
    (p.internet.fileUsb ? ", Kopie auf dem USB-Stick" : "")]);
  rows.push(...[
    ["Rechtliche Hinweise", `bestätigt (Version ${p.legal.version})`],
  ]);
  $("summary").replaceChildren(el("dl", {}, ...rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })])));
}

async function install() {
  $("install").disabled = true;
  $("install-error").textContent = "";
  lastPayload = payload();
  try {
    await api("/api/install", lastPayload);
    show("progress");
    poll();
  } catch (e) {
    $("install-error").textContent = e.message;
  } finally {
    $("install").disabled = false;
  }
}

// ------------------------------------------------------------ Fortschritt

async function poll() {
  clearTimeout(pollTimer);
  try {
    const data = await api("/api/status");
    const s = data.status;
    const pct = s.total ? Math.round((Math.max(s.step - 1, 0) / s.total) * 100) : 0;
    $("bar").style.width = (s.state === "done" ? 100 : pct) + "%";
    $("progress-text").textContent = s.total ? `Schritt ${s.step} von ${s.total}: ${s.title}` : "Starte …";
    $("log").textContent = data.log.join("\n");
    $("progress-error").textContent = s.state === "failed" ? s.error : "";
    $("progress-title").textContent = s.state === "failed" ? "Installation fehlgeschlagen" : "Installation läuft …";
    $("retry").hidden = s.state !== "failed" || !lastPayload;
    $("restart").hidden = s.state !== "failed" || !!lastPayload;
    if (s.mode) statusMode = s.mode;
    if (s.remote) statusRemote = s.remote;
    if (s.state === "done") { renderDone(); show("done"); return; }
    if (s.state === "failed") return;
  } catch (e) {
    $("progress-text").textContent = "Verbindung zum Pi unterbrochen – versuche es weiter …";
  }
  pollTimer = setTimeout(poll, 2000);
}

async function retry() {
  $("retry").hidden = true;
  try {
    await api("/api/install", lastPayload);
    poll();
  } catch (e) {
    $("progress-error").textContent = e.message;
    $("retry").hidden = false;
  }
}

function renderDone() {
  const net = info.network;
  const host = `${net.hostname}.local`;
  const m = (lastPayload && lastPayload.mode) || statusMode;
  const rem = (lastPayload && lastPayload.remote) || statusRemote || "rdp";
  const rows = [["Benutzer", info.user]];
  if (m !== "desktop" && rem === "browser") {
    const url = `https://${host}:8443`;
    rows.push(["Im Browser", el("a", { href: url, target: "_blank", rel: "noopener", text: url })]);
    rows.push(["Anmeldung", `Benutzer „${info.user}“ und dein Passwort`]);
    rows.push(["Beim ersten Öffnen", "Der Browser warnt einmal vor dem Zertifikat (es ist selbst ausgestellt): " +
      "„Erweitert“ → „Weiter zu kistengeist.local“. Danach Ton und Mikrofon im Browser erlauben."]);
  } else if (m !== "desktop") {   // RDP
    rows.push(["RDP-Adresse", net.ips.length ? `${net.ips[0]} oder ${host}` : host]);
    rows.push(["RDP-Programm", "Windows: „Remotedesktopverbindung“, Mac/Handy: „Windows App“"]);
    rows.push(["Verbindungsdatei", el("a", { href: "/kistengeist.rdp", download: "Kistengeist.rdp",
      text: "Kistengeist.rdp herunterladen (Ton, Mikrofon und Medientasten fertig eingestellt)" })]);
  }
  rows.push(["Erster Start", "Kistengeist öffnet Claude Desktop – melde dich dort mit deinem Claude-Konto an."]);
  rows.push(["Zugangsdaten", "Datei „Zugangsdaten.txt“ im Benutzerordner (Ports, Adressen, Logins)"]);
  const dd = (v) => (typeof v === "string" ? el("dd", { text: v }) : el("dd", {}, v));
  $("done-info").replaceChildren(el("dl", {}, ...rows.flatMap(([k, v]) => [el("dt", { text: k }), dd(v)])));
  api("/api/ports").then((d) => {
    const fw = d.ports.filter((x) => x.forward);
    if (d.access.public_url) rows.push(["Aus dem Internet", d.access.public_url]);
    if (d.access.n8n_url) rows.push(["n8n", d.access.n8n_url]);
    rows.push(["Am Router freigeben", fw.length ? fw.map((x) => `${x.proto} ${x.port}`).join(", ") + " → kistengeist" : "nichts"]);
    $("done-info").replaceChildren(el("dl", {}, ...rows.flatMap(([k, v]) => [el("dt", { text: k }), dd(v)])));
  }).catch(() => { /* optional */ });
}

async function reboot() {
  $("reboot").disabled = true;
  try {
    await api("/api/reboot", {});
    $("reboot").textContent = "Startet neu …";
  } catch (e) {
    $("reboot").disabled = false;
    alert(e.message);
  }
}

// ------------------------------------------------------------ Start

function wire() {
  $("welcome-next").addEventListener("click", () => { renderLegal(); show("legal"); });
  $("legal-next").addEventListener("click", () => { show("usb"); loadUsb(); });
  $("usb-refresh").addEventListener("click", loadUsb);
  $("usb-format").addEventListener("change", updateUsbOptions);
  $("usb-next").addEventListener("click", () => {
    const err = usbValid();
    $("usb-error").textContent = err;
    if (err) return;
    // Ohne Stick: Modul abwählen, mit Stick: anwählen.
    const byId = modulesById();
    if (byId["usb-stick"]) setChecked("usb-stick", !!usbPayload().device, byId);
    renderRemoteChoice();
    show("mode");
  });
  $("wifi-connect").addEventListener("click", connectWifi);
  for (const r of document.querySelectorAll("input[name=mode]")) r.addEventListener("change", renderRemoteChoice);
  for (const btn of document.querySelectorAll("[data-back]")) {
    btn.addEventListener("click", () => {
      let prev = PAGES[PAGES.indexOf(current) - 1];
      if (prev === "internet" && !needsInternet()) prev = "modules";
      if (prev === "modules") renderModules();
      show(prev);
    });
  }
  for (const btn of document.querySelectorAll("[data-next]")) {
    btn.addEventListener("click", () => {
      let next = PAGES[PAGES.indexOf(current) + 1];
      if (next === "internet" && !needsInternet()) next = "account";
      if (next === "internet") renderInternet();
      if (next === "modules") renderModules();
      if (next === "account") renderAccount();
      show(next);
    });
  }
  for (const r of document.querySelectorAll("input[name=net]")) r.addEventListener("change", renderInternet);
  for (const r of document.querySelectorAll("input[name=ddns]")) r.addEventListener("change", () => {
    $("ddns-result").textContent = "";
    renderInternet();
  });
  $("ddns-test").addEventListener("click", testDdns);
  $("internet-next").addEventListener("click", () => {
    const err = internetValid();
    $("internet-error").textContent = err;
    if (!err) { renderAccount(); show("account"); }
  });
  $("account-next").addEventListener("click", () => {
    const err = accountValid();
    $("account-error").textContent = err;
    if (!err) { renderSummary(); show("summary"); }
  });
  $("install").addEventListener("click", install);
  $("retry").addEventListener("click", retry);
  // Nach Neuladen der Seite fehlt die frühere Auswahl: neu eingeben lassen.
  $("restart").addEventListener("click", () => { renderLegal(); show("legal"); });
  $("reboot").addEventListener("click", reboot);
}

function normCode(v) {
  return (v || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

async function unlock() {
  const fromUrl = normCode(new URLSearchParams(location.search).get("code"));
  if (fromUrl) {
    setupCode = fromUrl;
    history.replaceState(null, "", location.pathname);   // Code nicht in Verlauf/Lesezeichen
  }
  for (;;) {
    if (setupCode) {
      try {
        await api("/api/code", {});
        try { sessionStorage.setItem("kg-code", setupCode); } catch (e) { /* egal */ }
        $("code-gate").hidden = true;
        return;
      } catch (e) {
        $("code-error").textContent = e.message;
      }
    }
    $("code-gate").hidden = false;
    $("code-input").focus();
    setupCode = await new Promise((resolve) => {
      $("code-form").onsubmit = (ev) => { ev.preventDefault(); resolve(normCode($("code-input").value)); };
    });
  }
}

async function init() {
  wire();
  for (const p of PAGES) $(`page-${p}`).hidden = true;
  await unlock();
  show("welcome");
  try {
    info = await api("/api/info");
  } catch (e) {
    $("net-status").textContent = "Der Setup-Assistent antwortet nicht: " + e.message;
    return;
  }
  $("version").textContent = info.version;
  $("user-name").textContent = info.user;
  for (const mod of info.modules) if (mod.default) selection.add(mod.id);
  fillSelect("locale", info.locales, "de_DE.UTF-8");
  fillSelect("keymap", info.keymaps, "de");
  fillSelect("timezone", info.timezones, "Europe/Berlin");
  renderNetwork();
  if (!info.network.online) {
    const timer = setInterval(async () => {
      try {
        info.network = (await api("/api/info")).network;
        renderNetwork();
        if (info.network.online) clearInterval(timer);
      } catch (e) { /* weiter warten */ }
    }, 10000);
  }

  const state = info.status.state;
  statusMode = info.status.mode || "";
  statusRemote = info.status.remote || "";
  if (state === "running" || state === "failed") { show("progress"); poll(); }
  if (state === "done") { renderDone(); show("done"); }
}

init();
