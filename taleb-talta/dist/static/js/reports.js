/* Scoped reports + CSV/XLSX downloads. */
(function () {
  "use strict";
  var meta = null, last = null;
  function params() {
    var f = document.getElementById("report-filters"), p = new URLSearchParams();
    ["date_from", "date_to", "course_id", "division_id", "custom_field", "custom_value"].forEach(function (k) { p.set(k, f.elements[k].value || ""); });
    return p;
  }
  async function run() {
    var kind = document.getElementById("report-kind").value;
    var out = await TT.api("/api/reports/" + kind + "?" + params().toString(), "GET");
    if (!out.success) return TT.toast(out.message, "error");
    last = out.data;
    document.getElementById("report-summary").textContent = TT.t("report.summary", { count: out.data.total }) + (out.data.truncated ? " " + TT.t("report.truncated") : "");
    document.getElementById("report-head").innerHTML = "<tr>" + out.data.columns.map(function (c) { return "<th>" + TT.esc(TT.t("report.column." + c)) + "</th>"; }).join("") + "</tr>";
    document.getElementById("report-body").innerHTML = out.data.rows.length ? out.data.rows.map(function (row) { return "<tr>" + row.map(function (v) { return "<td>" + TT.esc(v) + "</td>"; }).join("") + "</tr>"; }).join("") : '<tr><td colspan="' + out.data.columns.length + '" class="muted">' + TT.esc(TT.t("report.empty")) + '</td></tr>';
  }
  async function download(fmt) {
    var kind = document.getElementById("report-kind").value;
    var blob;
    try { blob = await TT.fetchBlob("/api/reports/" + kind + "/export/" + fmt + "?" + params().toString()); }
    catch (e) { return TT.toast(TT.t("err.use_chunked_download"), "error"); }
    var url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = kind + "." + fmt; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  document.addEventListener("DOMContentLoaded", async function () {
    var out = await TT.api("/api/reports/meta", "GET");
    if (!out.success) return TT.toast(out.message, "error");
    meta = out.data;
    document.getElementById("report-kind").innerHTML = meta.types.map(function (k) { return '<option value="' + k + '">' + TT.esc(TT.t("report." + k)) + '</option>'; }).join("");
    document.getElementById("report-course").innerHTML += meta.courses.map(function (c) { return '<option value="' + c.id + '">' + TT.esc(c.title) + '</option>'; }).join("");
    document.getElementById("report-division").innerHTML += meta.divisions.map(function (d) { return '<option value="' + d.id + '">' + TT.esc(d.name) + '</option>'; }).join("");
    var options = "";
    ["user", "course"].forEach(function (entity) { meta.fields[entity].forEach(function (f) { options += '<option value="' + entity + ":" + TT.esc(f.machine_name) + '">' + TT.esc(TT.t("customfield.entity_" + entity) + " · " + f.label) + '</option>'; }); });
    document.getElementById("report-field").innerHTML += options;
    var today = new Date(), prior = new Date(Date.now() - 30 * 86400000);
    document.getElementById("report-to").value = today.toISOString().slice(0, 10);
    document.getElementById("report-from").value = prior.toISOString().slice(0, 10);
    document.getElementById("report-filters").addEventListener("submit", function (ev) { ev.preventDefault(); run(); });
    document.getElementById("report-kind").addEventListener("change", function () {
      var audit = this.value === "audit";
      document.getElementById("report-field").closest(".field").hidden = audit;
      document.getElementById("report-value").closest(".field").hidden = audit;
    });
    document.getElementById("export-csv").addEventListener("click", function () { download("csv"); });
    document.getElementById("export-xlsx").addEventListener("click", function () { download("xlsx"); });
    run();
  });
})();
