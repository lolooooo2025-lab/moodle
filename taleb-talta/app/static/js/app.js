/* Taleb Talta — vanilla ES-module-free JS layer (no bundler, no CDN).
   All user-visible messages come from the API (already Egyptian Arabic).
   No hard-coded Arabic here (check_i18n). */
(function () {
  "use strict";
  var TT = window.TT || { sesskey: "" };
  var loadedAt = Date.now();

  function toast(msg, kind) {
    var region = document.getElementById("toast-region");
    if (!region || !msg) return;
    var el = document.createElement("div");
    el.className = "toast toast-" + (kind || "success");
    el.textContent = msg;
    region.appendChild(el);
    setTimeout(function () { el.remove(); }, 4500);
  }

  function showError(form, msg) {
    var box = form.querySelector(".form-error");
    if (box) { box.textContent = msg; box.hidden = false; }
    else { toast(msg, "error"); }
  }

  async function api(url, method, body) {
    var headers = { "Content-Type": "application/json" };
    if (method !== "GET") headers["X-Sesskey"] = TT.sesskey;
    var res = await fetch(url, {
      method: method,
      headers: headers,
      credentials: "same-origin",
      body: body ? JSON.stringify(body) : undefined
    });
    return res.json();
  }

  // Multipart upload (file + fields). Sesskey travels as a header.
  async function upload(url, formData) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "X-Sesskey": TT.sesskey },
      credentials: "same-origin",
      body: formData
    });
    return res.json();
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Expose a small, safe helper surface for page scripts.
  function translate(key, params) {
    var s = (window.TT_STRINGS || {})[key] || key;
    if (params) Object.keys(params).forEach(function (k) { s = s.split("{" + k + "}").join(String(params[k])); });
    return s;
  }

  TT.t = translate;
  TT.api = api;
  TT.upload = upload;
  TT.toast = toast;
  TT.esc = esc;
  window.TT = TT;

  function isEmbedded() {
    try { return window.self !== window.top; } catch (e) { return true; }
  }

  function showPreviewHelp(form) {
    var help = document.getElementById("preview-login-help");
    if (!help) return;
    var link = help.querySelector("a");
    link.href = window.location.origin + "/login";
    help.hidden = false;
    if (form) help.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  // Generic form -> API submission.
  function bindForm(form) {
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var url = form.getAttribute("data-api");
      var redirect = form.getAttribute("data-redirect");
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = v; });
      if (form.id === "register-form") {
        data.elapsed_ms = Date.now() - loadedAt;
        if (data.division_id) data.division_id = parseInt(data.division_id, 10);
      }
      var btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      try {
        var out = await api(url, "POST", data);
        if (out.success) {
          if (out.data && out.data.sesskey) TT.sesskey = out.data.sesskey;
          if (form.id === "login-form") {
            // A 200 login response is NOT proof that the browser retained the
            // cookie. Embedded previews can reject even partitioned cookies.
            // Verify the next request before showing success or navigating.
            var me = await api("/api/auth/me", "GET");
            if (!me.success) {
              showPreviewHelp(form);
              showError(form, translate("auth.preview_cookie_blocked"));
              return;
            }
            TT.sesskey = me.data.sesskey;
          }
          if (out.message) toast(out.message, "success");
          if (redirect) { setTimeout(function () { window.location.href = redirect; }, 400); }
          else if (form.id === "forgot-form") { form.reset(); }
        } else {
          showError(form, out.message);
        }
      } catch (e) {
        showError(form, "network");
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  }

  // Plugin manager actions.
  function bindPluginActions() {
    document.querySelectorAll("[data-plugin-action]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var row = btn.closest("tr");
        var component = row.getAttribute("data-component");
        var action = btn.getAttribute("data-plugin-action");
        var body = { component: component };
        if (action === "uninstall") body.purge = false;
        btn.disabled = true;
        try {
          var out = await api("/api/plugins/" + action, "POST", body);
          toast(out.message, out.success ? "success" : "error");
          if (out.success) setTimeout(function () { window.location.reload(); }, 600);
        } catch (e) { toast("network", "error"); }
        finally { btn.disabled = false; }
      });
    });
  }

  function bindLogout() {
    var btn = document.getElementById("logout-btn");
    if (!btn) return;
    btn.addEventListener("click", async function () {
      try { await api("/api/auth/logout", "POST", {}); } catch (e) {}
      window.location.href = "/login";
    });
  }

  function bindTheme() {
    var sel = document.getElementById("theme-select");
    if (!sel) return;
    sel.addEventListener("change", function () {
      document.documentElement.setAttribute("data-theme", sel.value);
      var https = window.location.protocol === "https:";
      document.cookie = "tt_theme=" + sel.value + ";path=/;max-age=31536000;" +
        (https ? "SameSite=None;Secure;Partitioned" : "SameSite=Lax");
    });
  }

  var lastNotifId = null;
  async function pollNotifications() {
    var badge = document.getElementById("notif-badge");
    if (!badge || !TT.sesskey) return;
    try {
      var out = await api("/api/notifications/unread", "GET");
      if (!out.success) return;
      badge.textContent = out.data.unread > 99 ? "99+" : String(out.data.unread);
      badge.hidden = out.data.unread === 0;
      var newest = out.data.latest.length ? out.data.latest[0].id : 0;
      if (lastNotifId !== null && newest > lastNotifId && "Notification" in window && Notification.permission === "granted" && document.hidden) {
        var n = out.data.latest[0];
        var reg = await navigator.serviceWorker.getRegistration();
        if (reg) reg.showNotification(n.title, { body: n.body, icon: "/static/icons/icon-192.png", data: { url: n.url }, tag: "tt-" + n.id });
      }
      lastNotifId = newest;
    } catch (e) {}
  }

  function registerSW() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[data-api]").forEach(bindForm);
    if (isEmbedded() && document.getElementById("login-form")) {
      showPreviewHelp(document.getElementById("login-form"));
    }
    bindPluginActions();
    bindLogout();
    bindTheme();
    document.querySelectorAll("[data-close-dialog]").forEach(function (btn) {
      btn.addEventListener("click", function () { btn.closest("dialog").close(); });
    });
    registerSW();
    pollNotifications();
    setInterval(pollNotifications, 30000);
  });
})();
