// Service worker: makes the app installable and usable offline.
// Strategy: NETWORK-FIRST for everything (always load the newest code/data when online; fall back to
// cache only when offline). This prevents the app ever getting stuck on a stale cached build.
const SHELL = "mt-shell-v15";
const SHELL_FILES = ["./", "./index.html", "./style.css", "./app.js", "./manifest.json",
  "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
// Web push: the installed app shows the notification itself (no ntfy app needed).
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data.json(); } catch { d = { title: "Market Tracker", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Market Tracker", {
    body: d.body || "", icon: "icon-192.png", badge: "icon-192.png",
    data: { url: d.url || "./" }, tag: "daily-top5", renotify: true,
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    for (const c of cs) if ("focus" in c) return c.focus();
    return clients.openWindow(e.notification.data && e.notification.data.url || "./");
  }));
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  // Network-first: always try the live file; cache a copy; use cache only if the network fails (offline).
  e.respondWith(
    fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(SHELL).then(c => c.put(e.request, copy)).catch(() => {});
      return r;
    }).catch(() => caches.match(e.request))
  );
});
