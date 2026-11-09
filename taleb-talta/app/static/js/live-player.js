(function () {
  "use strict";
  var stream = null, hls = null, lastMessage = 0, chatTimer = null;
  function attach(url) {
    var video = document.getElementById("live-video");
    if (hls) { hls.destroy(); hls = null; }
    video.removeAttribute("src"); video.load();
    if (!url) return;
    if (url.indexOf(".m3u8") !== -1 && window.Hls && Hls.isSupported()) {
      hls = new Hls({ enableWorker: true }); hls.loadSource(url); hls.attachMedia(video);
    } else { video.src = url; }
  }
  function renderStatus() {
    document.getElementById("live-title").textContent = stream.title;
    document.getElementById("live-crumb").textContent = stream.title;
    document.getElementById("live-description").textContent = stream.description;
    var badge = document.getElementById("live-status");
    badge.textContent = TT.t(stream.status === "live" ? "live.live" : "stream." + stream.status);
    badge.className = "badge badge-" + (stream.status === "live" ? "approved" : "pending");
    var waiting = document.getElementById("live-waiting");
    waiting.hidden = stream.status === "live";
    waiting.textContent = TT.t(stream.status === "scheduled" ? "live.scheduled" : "stream." + stream.status);
    document.getElementById("live-video").hidden = stream.status !== "live";
    var canChat = stream.can_chat;
    document.getElementById("live-chat-form").hidden = !canChat;
    document.getElementById("live-chat-closed").hidden = canChat;
    attach(stream.playback_url);
  }
  async function loadStream() {
    var out = await TT.api("/api/streams/" + TT.page.streamId, "GET");
    if (!out.success) { TT.toast(out.message, "error"); return; }
    var changed = !stream || stream.status !== out.data.status || stream.playback_url !== out.data.playback_url;
    stream = out.data; if (changed) renderStatus();
  }
  function messageHTML(m) {
    return '<article class="live-message"><strong class="small">' + TT.esc(m.author) + '</strong><p class="pre-wrap m-0">' + TT.esc(m.body) + '</p></article>';
  }
  async function pollChat() {
    if (!stream || !stream.chat_channel_id) return;
    var out = await TT.api("/api/chat/channels/" + stream.chat_channel_id + "/messages?after_id=" + lastMessage + "&limit=100", "GET");
    if (!out.success) return;
    var list = document.getElementById("live-messages");
    if (out.data.messages.length) {
      list.insertAdjacentHTML("beforeend", out.data.messages.map(messageHTML).join(""));
      lastMessage = out.data.messages[out.data.messages.length - 1].id;
      list.scrollTop = list.scrollHeight;
    }
    if (out.data.channel && !out.data.channel.can_send) {
      document.getElementById("live-chat-form").hidden = true;
      document.getElementById("live-chat-closed").hidden = false;
    }
  }
  document.addEventListener("DOMContentLoaded", async function () {
    await loadStream(); await pollChat();
    setInterval(loadStream, 10000); chatTimer = setInterval(pollChat, 3000);
    document.getElementById("live-chat-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); var input = document.getElementById("live-chat-input");
      if (!input.value.trim() || !stream.can_chat) return;
      var out = await TT.api("/api/chat/channels/" + stream.chat_channel_id + "/messages", "POST", { body: input.value });
      if (out.success) { input.value = ""; pollChat(); } else TT.toast(out.message, "error");
    });
    window.addEventListener("beforeunload", function () { if (hls) hls.destroy(); clearInterval(chatTimer); });
  });
})();
