/* Course detail — enrolment, manual purchase requests, pricing, lessons. */
(function () {
  "use strict";
  var L = (window.TT && TT.labels) || {};
  var courseId = TT.page.courseId, course = null, purchaseTarget = null, priceTarget = null;
  function money(c) { return new Intl.NumberFormat("ar-EG", { style: "currency", currency: "EGP" }).format(c / 100); }
  function lessonRow(les) {
    var prog = les.progress || 0;
    var right = !les.locked
      ? '<a class="btn btn-primary btn-sm" href="/learn/' + les.id + '">' + (prog >= 100 ? L.done : L.start) + "</a>"
      : (les.price_cents > 0 ? '<button class="btn btn-accent btn-sm" data-buy-lesson="' + les.id + '">' + L.buy + " · " + money(les.price_cents) + '</button>' : '<span class="badge badge-pending">' + L.locked + "</span>");
    var bar = !les.locked ? '<div class="progress w-140"><span data-progress="' + prog + '"></span></div>' : "";
    var price = course.can_price ? '<button class="btn btn-ghost btn-sm" data-price-lesson="' + les.id + '" data-price="' + les.price_cents + '">' + L.lessonPrice + (les.price_cents ? ": " + money(les.price_cents) : "") + '</button>' : (les.price_cents > 0 ? '<span class="chip">' + money(les.price_cents) + '</span>' : "");
    return '<div class="lesson-row"><div class="flex-1"><div class="lesson-title">' + TT.esc(les.title) + "</div>" +
      (les.summary ? '<div class="muted small">' + TT.esc(les.summary) + "</div>" : "") + "</div>" +
      '<div class="row">' + price + bar + right + "</div></div>";
  }
  async function openPurchase(lessonId) {
    purchaseTarget = { course_id: courseId, lesson_id: lessonId || 0 };
    var meta = await TT.api("/api/purchases/meta", "GET");
    var box = document.getElementById("purchase-support");
    box.textContent = meta.success ? (L.supportPhone + ": " + (meta.data.support_phone || "—") + " · " + (meta.data.support_message || L.noGateway)) : L.noGateway;
    document.getElementById("purchase-form").reset();
    document.getElementById("purchase-dialog").showModal();
  }
  function openPrice(type, id, cents) {
    priceTarget = { type: type, id: id };
    document.getElementById("price-dialog-title").textContent = type === "course" ? L.coursePrice : L.lessonPrice;
    document.getElementById("price-input").value = (cents / 100).toFixed(2);
    document.getElementById("price-dialog").showModal();
  }
  async function load() {
    var out = await TT.api("/api/courses/" + courseId + "/detail", "GET");
    if (!out.success) { TT.toast(out.message || L.generic, "error"); return; }
    course = out.data; var c = course;
    document.getElementById("crumb-title").textContent = c.title;
    document.getElementById("course-title").textContent = c.title;
    document.getElementById("course-summary").textContent = c.summary || "";
    var actions = document.getElementById("course-actions");
    var html = "";
    if (c.price_cents > 0) html += '<span class="chip">' + L.coursePrice + ": " + money(c.price_cents) + '</span> ';
    if (!c.can_learn && c.price_cents > 0) html += '<button class="btn btn-accent" id="buy-course">' + L.buy + "</button> ";
    if (!c.enrolled && c.price_cents === 0 && !c.can_edit) html += '<button class="btn btn-accent" id="enrol-btn">' + L.enroll + "</button>";
    if (c.can_price) html += ' <button class="btn btn-ghost btn-sm" id="price-course">' + L.coursePrice + "</button>";
    actions.innerHTML = html;
    var enrol = document.getElementById("enrol-btn");
    if (enrol) enrol.addEventListener("click", async function () { var r = await TT.api("/api/courses/" + courseId + "/enrol", "POST", {}); TT.toast(r.message, r.success ? "success" : "error"); if (r.success) load(); });
    var buy = document.getElementById("buy-course"); if (buy) buy.addEventListener("click", function () { openPurchase(0); });
    var price = document.getElementById("price-course"); if (price) price.addEventListener("click", function () { openPrice("course", courseId, c.price_cents); });
    var wrap = document.getElementById("sections"), empty = document.getElementById("course-empty"), sectionsHtml = "";
    if (c.can_edit) sectionsHtml += '<div class="card mb-1"><div class="row"><input id="new-section-title" type="text" class="input-inline flex-1 min-w-200" placeholder="' + L.sectionTitle + '"><button class="btn btn-primary btn-sm" id="add-section-btn">' + L.newSection + "</button></div></div>";
    if (!c.sections.length && !c.can_edit) { wrap.innerHTML = ""; empty.hidden = false; return; }
    empty.hidden = true;
    sectionsHtml += c.sections.map(function (s) {
      var rows = s.lessons.length ? s.lessons.map(lessonRow).join("") : '<div class="lesson-row"><span class="muted">' + L.noLessons + "</span></div>";
      var addLesson = c.can_edit ? '<div class="lesson-row"><input type="text" data-lesson-input="' + s.id + '" class="input-inline flex-1" placeholder="' + L.lessonTitle + '"><button class="btn btn-ghost btn-sm" data-add-lesson="' + s.id + '">' + L.newLesson + "</button></div>" : "";
      return '<details class="section-block" open><summary><span>' + TT.esc(s.title) + '</span><span class="muted small">' + s.lessons.length + "</span></summary>" + rows + addLesson + "</details>";
    }).join("");
    wrap.innerHTML = sectionsHtml;
    wrap.querySelectorAll("[data-progress]").forEach(function (el) { el.style.width = el.getAttribute("data-progress") + "%"; });
    wrap.querySelectorAll("[data-buy-lesson]").forEach(function (b) { b.addEventListener("click", function () { openPurchase(Number(b.dataset.buyLesson)); }); });
    wrap.querySelectorAll("[data-price-lesson]").forEach(function (b) { b.addEventListener("click", function () { openPrice("lesson", Number(b.dataset.priceLesson), Number(b.dataset.price)); }); });
    bindStaff(c);
  }
  function bindStaff(c) {
    if (!c.can_edit) return;
    var addSec = document.getElementById("add-section-btn");
    if (addSec) addSec.addEventListener("click", async function () { var out = await TT.api("/api/courses/" + courseId + "/sections", "POST", { title: document.getElementById("new-section-title").value }); TT.toast(out.message, out.success ? "success" : "error"); if (out.success) load(); });
    document.querySelectorAll("[data-add-lesson]").forEach(function (b) { b.addEventListener("click", async function () { var sid = b.getAttribute("data-add-lesson"); var input = document.querySelector('[data-lesson-input="' + sid + '"]'); var out = await TT.api("/api/sections/" + sid + "/lessons", "POST", { title: input.value }); TT.toast(out.message, out.success ? "success" : "error"); if (out.success) load(); }); });
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("purchase-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); if (!purchaseTarget) return;
      var data = Object.assign({}, purchaseTarget, { reference: document.getElementById("purchase-reference").value, note: document.getElementById("purchase-note").value });
      var out = await TT.api("/api/purchases", "POST", data);
      TT.toast(out.message, out.success ? "success" : "error");
      if (out.success) { document.getElementById("purchase-dialog").close(); window.location.href = "/purchases"; }
    });
    document.getElementById("price-form").addEventListener("submit", async function (ev) {
      ev.preventDefault(); if (!priceTarget) return;
      var cents = Math.round(Number(document.getElementById("price-input").value) * 100);
      var url = priceTarget.type === "course" ? "/api/courses/" + priceTarget.id + "/pricing" : "/api/lessons/" + priceTarget.id + "/pricing";
      var out = await TT.api(url, "POST", { price_cents: cents });
      TT.toast(out.message, out.success ? "success" : "error"); if (out.success) { document.getElementById("price-dialog").close(); load(); }
    });
    load();
  });
})();
