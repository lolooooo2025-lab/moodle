(function () {
  "use strict";
  function urlBase64ToUint8Array(base64) {
    var padding = "=".repeat((4 - base64.length % 4) % 4);
    var raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); });
  }
  async function load() {
    var out = await TT.api("/api/notifications", "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    var list = document.getElementById("notification-list");
    document.getElementById("notifications-empty").hidden = out.data.rows.length > 0;
    list.innerHTML = out.data.rows.map(function (n) {
      return '<article class="card notification-card' + (n.read ? '' : ' unread') + '" data-notification="' + n.id + '"><div class="spread"><h2 class="m-0">' + TT.esc(n.title) + '</h2><span class="badge">' + TT.t(n.kind === "campaign" ? "notif.friday" : "notif.new") + '</span></div><p class="pre-wrap">' + TT.esc(n.body) + '</p><div class="spread"><time class="muted small">' + new Date(n.created_at).toLocaleString("ar-EG") + '</time><div class="row"><a class="btn btn-ghost btn-sm" href="' + TT.esc(n.url) + '">' + TT.t("nav.open") + '</a>' + (n.read ? '' : '<button class="btn btn-primary btn-sm" data-read="' + n.id + '">' + TT.t("notif.mark_read") + '</button>') + '</div></div></article>';
    }).join("");
    list.querySelectorAll("[data-read]").forEach(function (b) { b.addEventListener("click", async function () {
      var r = await TT.api("/api/notifications/" + b.dataset.read + "/read", "POST", {});
      TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load();
    }); });
  }
  async function enablePush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) { TT.toast(TT.t("notif.push_unsupported"), "error"); return; }
    var permission = await Notification.requestPermission();
    if (permission !== "granted") { TT.toast(TT.t("notif.push_denied"), "error"); return; }
    var reg = await navigator.serviceWorker.ready;
    var key = await TT.api("/api/notifications/push/key", "GET");
    if (!key.success) { TT.toast(key.message, "error"); return; }
    var sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key.data.public_key) });
    var json = sub.toJSON();
    var out = await TT.api("/api/notifications/push/subscribe", "POST", { endpoint: sub.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth });
    TT.toast(out.message, out.success ? "success" : "error");
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("mark-all").addEventListener("click", async function () { var r = await TT.api("/api/notifications/read-all", "POST", {}); TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load(); });
    document.getElementById("push-enable").addEventListener("click", function () { enablePush().catch(function () { TT.toast(TT.t("notif.push_unsupported"), "error"); }); });
    load();
  });
})();
