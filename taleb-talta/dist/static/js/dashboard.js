/* Per-user dashboard block order/visibility. */
(function () {
  "use strict";
  var blocks = [];
  function draw() {
    var list = document.getElementById("dashboard-block-list");
    list.innerHTML = blocks.map(function (b, i) {
      return '<div class="builder-row" data-key="' + TT.esc(b.key) + '"><label class="check-row"><input type="checkbox" data-block-enabled ' + (b.enabled ? "checked" : "") + '> ' + TT.esc(TT.t("dashboard.block_" + b.key)) + '</label><span class="actions"><button type="button" class="btn btn-ghost btn-sm" data-move="-1" ' + (i === 0 ? "disabled" : "") + '>' + TT.esc(TT.t("misc.up")) + '</button><button type="button" class="btn btn-ghost btn-sm" data-move="1" ' + (i === blocks.length - 1 ? "disabled" : "") + '>' + TT.esc(TT.t("misc.down")) + '</button></span></div>';
    }).join("");
    list.querySelectorAll("[data-move]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var row = btn.closest(".builder-row");
        var index = blocks.findIndex(function (b) { return b.key === row.getAttribute("data-key"); });
        var target = index + parseInt(btn.getAttribute("data-move"), 10);
        var tmp = blocks[index]; blocks[index] = blocks[target]; blocks[target] = tmp;
        blocks.forEach(function (b, i2) { b.order = i2; });
        draw();
      });
    });
    list.querySelectorAll("[data-block-enabled]").forEach(function (cb) {
      cb.addEventListener("change", function () {
        var key = cb.closest(".builder-row").getAttribute("data-key");
        blocks.find(function (b) { return b.key === key; }).enabled = cb.checked;
      });
    });
  }
  document.addEventListener("DOMContentLoaded", function () {
    var dialog = document.getElementById("dashboard-dialog");
    document.getElementById("customize-dashboard").addEventListener("click", async function () {
      var out = await TT.api("/api/dashboard", "GET");
      if (!out.success) return TT.toast(out.message, "error");
      blocks = out.data; draw(); dialog.showModal();
    });
    document.getElementById("save-dashboard").addEventListener("click", async function () {
      var out = await TT.api("/api/dashboard/preferences", "POST", { blocks: blocks });
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) setTimeout(function () { location.reload(); }, 500);
    });
  });
})();
