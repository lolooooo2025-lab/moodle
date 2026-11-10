/* Messages + channels. Cursor polling, private uploads, approved stickers,
   contacts and blocking. No browser-to-browser sockets or public file URLs. */
(function () {
  "use strict";
  var L = TT.labels;
  var channels = [], current = null, lastId = 0, oldestId = 0, polling = false;
  var attachment = null, sticker = null, foundContact = null, addingMembers = false;
  var list = document.getElementById("message-list");
  var body = document.getElementById("message-body");
  var sendBtn = document.getElementById("send-btn");
  function el(id) { return document.getElementById(id); }
  function kindLabel(kind) { return L[kind] || kind; }
  function show(out) { TT.toast(out.message || L.generic, out.success ? "success" : "error"); return out.success; }
  function channelRow(c) {
    return '<button type="button" class="channel-row' + (current && current.id === c.id ? ' selected' : '') + '" data-channel="' + c.id + '">' +
      '<span class="channel-kind">' + TT.esc(kindLabel(c.kind)) + '</span><strong>' + TT.esc(c.title) + '</strong>' +
      '<span class="channel-preview">' + TT.esc(c.last_message || L.noMessages) + '</span>' +
      (c.unread ? '<span class="badge badge-approved unread-badge">' + c.unread + '</span>' : '') + '</button>';
  }
  async function loadChannels() {
    var out = await TT.api("/api/chat/channels?kind=" + encodeURIComponent(el("channel-filter").value), "GET");
    if (!out.success) return;
    channels = out.data;
    el("channel-list").innerHTML = channels.map(channelRow).join("");
    el("channels-empty").hidden = channels.length > 0;
    el("channel-list").querySelectorAll("[data-channel]").forEach(function (btn) {
      btn.addEventListener("click", function () { selectChannel(Number(btn.dataset.channel)); });
    });
    if (current) {
      var updated = channels.find(function (c) { return c.id === current.id; });
      if (updated) updateHead(updated);
    }
  }
  async function loadContacts() {
    var out = await TT.api("/api/messages/contacts", "GET");
    if (!out.success) return;
    el("contact-list").innerHTML = out.data.map(function (c) {
      return '<button class="contact-row" data-contact="' + c.channel_id + '"><span>' + TT.esc(c.name) + '</span>' +
        (c.blocked ? '<span class="muted small">' + TT.esc(L.blocked) + '</span>' : '') + '</button>';
    }).join("");
    el("contacts-empty").hidden = out.data.length > 0;
    el("contact-list").querySelectorAll("[data-contact]").forEach(function (btn) {
      btn.addEventListener("click", function () { selectChannel(Number(btn.dataset.contact)); });
    });
  }
  function attachmentHTML(a) {
    var url = TT.esc(a.url), name = TT.esc(a.name);
    if (a.mime.indexOf("image/") === 0) return '<a href="' + url + '" target="_blank" rel="noopener"><img class="message-image" src="' + url + '" alt="' + name + '" loading="lazy"></a>';
    if (a.mime.indexOf("video/") === 0) return '<video class="message-video" controls preload="metadata" src="' + url + '" aria-label="' + name + '"></video>';
    return '<a class="file-chip" href="' + url + '">' + TT.esc(L.download) + ': ' + name + '</a>';
  }
  function messageHTML(m) {
    var content = m.body ? '<p class="pre-wrap m-0">' + TT.esc(m.body) + '</p>' : "";
    if (m.attachment) content += attachmentHTML(m.attachment);
    if (m.sticker) content += '<img class="message-sticker" src="' + TT.esc(m.sticker.url) + '" alt="' + TT.esc(m.sticker.title) + '">';
    return '<article class="message-bubble' + (m.sender_id === TT.page.userId ? ' mine' : '') + '" data-message="' + m.id + '">' +
      '<div class="spread"><strong class="small">' + TT.esc(m.author) + '</strong><time class="muted tiny">' + TT.community.fmtDate(m.created_at) + '</time></div>' + content +
      (m.sender_id !== TT.page.userId ? '<button class="message-report" data-report="' + m.id + '">' + TT.esc(L.report) + '</button>' : '') + '</article>';
  }
  function bindReports(root) {
    root.querySelectorAll("[data-report]").forEach(function (btn) {
      if (btn.dataset.bound) return; btn.dataset.bound = "1";
      btn.addEventListener("click", function () { TT.community.report("chat_message", btn.dataset.report); });
    });
  }
  function updateHead(c) {
    current = c;
    el("conversation-title").textContent = c.title;
    el("conversation-meta").textContent = kindLabel(c.kind) + (c.kind !== "private" ? " · " + L.members + ": " + c.members.length : "");
    el("block-btn").hidden = c.kind !== "private" || (c.blocked && !c.blocked_by_me);
    el("block-btn").textContent = c.blocked_by_me ? L.unblock : L.block;
    el("add-members-btn").hidden = !c.can_add;
    el("chat-blocked-notice").hidden = !c.blocked;
    var canSend = c.can_send !== false && !c.blocked && !el("chat-restriction").dataset.active;
    sendBtn.disabled = !canSend; body.disabled = !canSend;
    el("chat-file").disabled = !canSend; el("stickers-btn").disabled = !canSend;
    var receipt = el("read-receipt");
    if (receipt) receipt.remove();
    if (c.kind === "private" && lastId && lastId <= (c.peer_last_read_id || 0)) {
      var r = document.createElement("p"); r.id = "read-receipt"; r.className = "muted tiny read-receipt"; r.textContent = L.read;
      list.insertAdjacentElement("afterend", r);
    }
  }
  async function selectChannel(id) {
    attachment = null; sticker = null; renderPending();
    el("chat-placeholder").hidden = true; el("conversation").hidden = false;
    el("sticker-picker").hidden = true; list.innerHTML = ""; lastId = 0; oldestId = 0;
    current = { id: id, kind: "group", title: "", members: [] };
    await loadHistory(0);
    await loadChannels();
  }
  async function loadHistory(before) {
    var id = current.id;
    var out = await TT.api("/api/chat/channels/" + id + "/messages?limit=50" + (before ? "&before_id=" + before : ""), "GET");
    if (!out.success || id !== current.id) { if (!out.success) show(out); return; }
    var rows = out.data.messages;
    if (before) {
      list.insertAdjacentHTML("afterbegin", rows.map(messageHTML).join(""));
      if (rows.length) oldestId = rows[0].id;
    } else {
      list.innerHTML = rows.map(messageHTML).join("");
      if (rows.length) { oldestId = rows[0].id; lastId = rows[rows.length - 1].id; }
      list.scrollTop = list.scrollHeight;
    }
    el("older-btn").hidden = !out.data.has_more;
    el("messages-empty").hidden = rows.length > 0 || before > 0;
    updateHead(out.data.channel); bindReports(list);
    if (lastId && !document.hidden) await markRead();
  }
  async function markRead() {
    if (!current || !lastId) return;
    await TT.api("/api/chat/channels/" + current.id + "/read", "POST", { message_id: lastId });
  }
  async function poll() {
    if (polling || document.hidden) return;
    polling = true;
    try {
      if (current && current.id) {
        var out = await TT.api("/api/chat/channels/" + current.id + "/messages?after_id=" + lastId, "GET");
        if (out.success) {
          var rows = out.data.messages.filter(function (m) { return m.id > lastId && !list.querySelector('[data-message="' + m.id + '"]'); });
          if (rows.length) {
            var nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 100;
            list.insertAdjacentHTML("beforeend", rows.map(messageHTML).join(""));
            lastId = rows[rows.length - 1].id; if (!oldestId) oldestId = rows[0].id;
            el("messages-empty").hidden = true; bindReports(list);
            if (nearBottom) list.scrollTop = list.scrollHeight;
            await markRead();
          }
          updateHead(out.data.channel);
        }
      }
      await loadChannels();
    } catch (e) {}
    finally { polling = false; }
  }
  function renderPending() {
    el("pending-attachment").hidden = !attachment;
    el("pending-attachment-name").textContent = attachment ? L.attachmentReady + ": " + attachment.name : "";
    el("pending-sticker").hidden = !sticker;
    if (sticker) { el("pending-sticker-image").src = sticker.url; el("pending-sticker-image").alt = sticker.title; }
    else el("pending-sticker-image").removeAttribute("src");
  }
  async function sendMessage(ev) {
    ev.preventDefault();
    if (!current || (!body.value.trim() && !attachment && !sticker)) return;
    sendBtn.disabled = true;
    try {
      var out = await TT.api("/api/chat/channels/" + current.id + "/messages", "POST", {
        body: body.value.trim(), attachment_id: attachment ? attachment.id : null, sticker_id: sticker ? sticker.id : null
      });
      if (out.success) {
        body.value = ""; attachment = null; sticker = null; renderPending();
        var m = out.data.message;
        if (m.id > lastId) { list.insertAdjacentHTML("beforeend", messageHTML(m)); lastId = m.id; if (!oldestId) oldestId = m.id; bindReports(list); }
        el("messages-empty").hidden = true; list.scrollTop = list.scrollHeight;
        if (out.data.warning) TT.toast(out.data.warning, "error");
        await loadChannels();
      } else show(out);
    } catch (e) { TT.toast(L.generic, "error"); }
    finally { sendBtn.disabled = body.disabled; }
  }
  async function lookupPhones(text) {
    var phones = text.split(/\n|,/).map(function (s) { return s.trim(); }).filter(Boolean);
    if (!phones.length || phones.length > 49) throw new Error(L.generic);
    var ids = [];
    for (var i = 0; i < phones.length; i++) {
      var out = await TT.api("/api/messages/find?phone=" + encodeURIComponent(phones[i]), "GET");
      if (!out.success) throw new Error(out.message);
      if (ids.indexOf(out.data.user_id) < 0) ids.push(out.data.user_id);
    }
    return ids;
  }
  async function loadStickers() {
    var out = await TT.api("/api/stickers", "GET");
    if (!out.success) return;
    el("sticker-grid").innerHTML = out.data.map(function (s) {
      return '<button class="sticker-option" data-sticker="' + s.id + '" data-url="' + TT.esc(s.url) + '" data-title="' + TT.esc(s.title) + '"><img src="' + TT.esc(s.url) + '" alt="' + TT.esc(s.title) + '"><span class="small">' + TT.esc(s.title) + '</span></button>';
    }).join("");
    el("stickers-empty").hidden = out.data.length > 0;
    el("sticker-grid").querySelectorAll("[data-sticker]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        sticker = { id: Number(btn.dataset.sticker), url: btn.dataset.url, title: btn.dataset.title };
        renderPending(); el("sticker-picker").hidden = true; body.focus();
      });
    });
  }
  document.addEventListener("DOMContentLoaded", async function () {
    TT.community.bindDialogs();
    el("refresh-channels").addEventListener("click", function () { loadChannels(); loadContacts(); });
    el("channel-filter").addEventListener("change", loadChannels);
    el("older-btn").addEventListener("click", function () { loadHistory(oldestId); });
    el("send-form").addEventListener("submit", sendMessage);
    el("remove-attachment").addEventListener("click", function () { attachment = null; renderPending(); });
    el("remove-sticker").addEventListener("click", function () { sticker = null; renderPending(); });
    el("chat-file").addEventListener("change", async function () {
      var file = this.files[0]; if (!file || !current) return;
      var fd = new FormData(); fd.append("upload", file);
      var out = await TT.upload("/api/chat/attachments", fd);
      if (show(out)) { attachment = out.data; renderPending(); }
      this.value = "";
    });
    el("stickers-btn").addEventListener("click", function () { el("sticker-picker").hidden = !el("sticker-picker").hidden; if (!el("sticker-picker").hidden) loadStickers(); });
    el("close-stickers").addEventListener("click", function () { el("sticker-picker").hidden = true; });
    el("block-btn").addEventListener("click", async function () {
      if (!current.peer_id) return;
      var action = current.blocked_by_me ? "unblock" : "block";
      if (action === "block" && !window.confirm(L.confirm)) return;
      var out = await TT.api("/api/messages/" + action, "POST", { user_id: current.peer_id });
      if (show(out)) { await loadChannels(); await loadContacts(); }
    });
    el("find-contact-btn").addEventListener("click", function () { foundContact = null; el("contact-result").hidden = true; el("start-contact").hidden = true; el("contact-dialog").showModal(); });
    el("contact-form").addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var out = await TT.api("/api/messages/find?phone=" + encodeURIComponent(el("contact-phone").value.trim()), "GET");
      if (out.success) { foundContact = out.data; el("contact-result").textContent = out.data.name; el("contact-result").hidden = false; el("start-contact").hidden = false; }
      else { foundContact = null; el("start-contact").hidden = true; show(out); }
    });
    el("start-contact").addEventListener("click", async function () {
      if (!foundContact) return;
      var out = await TT.api("/api/messages/start", "POST", { user_id: foundContact.user_id });
      if (show(out)) { el("contact-dialog").close(); await loadContacts(); await selectChannel(out.data.channel_id); }
    });
    function openGroup(addMode) {
      addingMembers = addMode;
      el("group-dialog-title").textContent = addMode ? L.addMembers : L.newGroup;
      el("group-title-field").hidden = addMode; el("group-title").required = !addMode;
      el("group-form").querySelector('[type="submit"]').textContent = addMode ? L.add : L.newGroup;
      el("group-phones").value = ""; el("group-dialog").showModal();
    }
    el("new-group-btn").addEventListener("click", function () { openGroup(false); });
    el("add-members-btn").addEventListener("click", function () { openGroup(true); });
    el("group-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var btn = this.querySelector('[type="submit"]'); btn.disabled = true;
      try {
        var ids = await lookupPhones(el("group-phones").value);
        var out = addingMembers ? await TT.api("/api/chat/channels/" + current.id + "/members", "POST", { user_ids: ids }) :
          await TT.api("/api/chat/groups", "POST", { title: el("group-title").value.trim(), member_ids: ids });
        if (show(out)) { el("group-dialog").close(); await loadChannels(); if (!addingMembers) await selectChannel(out.data.channel_id); }
      } catch (e) { TT.toast(e.message || L.generic, "error"); }
      finally { btn.disabled = false; }
    });
    el("add-sticker-btn").addEventListener("click", function () { el("sticker-dialog").showModal(); });
    el("sticker-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var file = el("sticker-file").files[0]; if (!file) return;
      var fd = new FormData(); fd.append("title", el("sticker-title").value.trim()); fd.append("upload", file);
      var btn = this.querySelector('[type="submit"]'); btn.disabled = true;
      var out = await TT.upload("/api/stickers", fd); btn.disabled = false;
      if (show(out)) { el("sticker-dialog").close(); this.reset(); }
    });
    el("my-stickers-btn").addEventListener("click", async function () {
      var out = await TT.api("/api/stickers?mine=true", "GET");
      if (out.success) el("my-stickers-list").innerHTML = out.data.map(function (s) {
        return '<div class="row"><img class="sticker-thumb" src="' + TT.esc(s.url) + '" alt="' + TT.esc(s.title) + '"><span>' + TT.esc(s.title) + '</span><span class="badge">' + TT.esc(L[s.status] || s.status) + '</span></div>';
      }).join("") || '<p class="muted">' + TT.esc(L.noStickers) + '</p>';
      el("my-stickers-dialog").showModal();
    });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) poll(); });
    try {
      var me = await TT.api("/api/auth/me", "GET");
      if (me.success && me.data.restricted) {
        el("chat-restriction").hidden = false; el("chat-restriction").dataset.active = "1";
        el("chat-restriction-until").textContent = L.until + " " + TT.community.fmtDate(me.data.restricted_until);
      }
      await loadChannels(); await loadContacts();
      if (TT.page.initialChannel) await selectChannel(TT.page.initialChannel);
      else {
        var priv = channels.find(function (c) { return c.kind === "private"; }) || channels[0];
        if (priv) await selectChannel(priv.id);
      }
      setInterval(poll, 5000);
    } catch (e) { TT.toast(L.generic, "error"); }
  });
})();
