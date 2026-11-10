/* Taleb Talta service worker — caches STATIC ASSETS ONLY.
   Never caches authenticated HTML or API responses (prompt trap #12):
   a shared device must never serve one student's data to the next user. */
var CACHE = "tt-static-v8";
var PRECACHE = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/community.js",
  "/static/js/forum.js",
  "/static/js/thread.js",
  "/static/js/chat.js",
  "/static/js/moderation.js",
  "/static/logo.png",
  "/static/fonts/cairo-arabic-400-normal.woff2",
  "/static/fonts/cairo-arabic-700-normal.woff2",
  "/static/fonts/cairo-latin-400-normal.woff2",
  "/static/fonts/cairo-latin-700-normal.woff2"
];

self.addEventListener("install", function (ev) {
  ev.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(PRECACHE); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (ev) {
  ev.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (ev) {
  var url = new URL(ev.request.url);
  // Only same-origin GET static assets are cacheable. Everything else
  // (pages, /api/*, fonts outside /static, navigations) goes to the network.
  if (ev.request.method !== "GET" || url.origin !== self.location.origin ||
      url.pathname.indexOf("/static/") !== 0) {
    return; // fall through to network, no cache write
  }
  // Network-first so login/session fixes reach an already-installed client
  // promptly; the cache remains an offline fallback for static assets only.
  ev.respondWith(fetch(ev.request).then(function (res) {
    if (res && res.status === 200) {
      var clone = res.clone();
      caches.open(CACHE).then(function (c) { c.put(ev.request, clone); });
    }
    return res;
  }).catch(function () { return caches.match(ev.request); }));
});


self.addEventListener("push", function (ev) {
  var data = {};
  try { data = ev.data ? ev.data.json() : {}; } catch (e) { return; }
  var title = data.title || "Taleb Talta";
  ev.waitUntil(self.registration.showNotification(title, {
    body: data.body || "", icon: "/static/icons/icon-192.png", badge: "/static/icons/icon-192.png",
    data: { url: data.url || "/notifications" }, tag: "tt-" + (data.notification_id || Date.now())
  }));
});

self.addEventListener("notificationclick", function (ev) {
  ev.notification.close();
  var path = (ev.notification.data && ev.notification.data.url) || "/notifications";
  if (path.charAt(0) !== "/" || path.charAt(1) === "/") path = "/notifications";
  var target = self.location.origin + path;
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].url.indexOf(self.location.origin) === 0 && "focus" in list[i]) {
        list[i].navigate(target); return list[i].focus();
      }
    }
    return self.clients.openWindow(target);
  }));
});
