/* Shared renderer for admin-defined fields. Values are data, never HTML. */
(function () {
  "use strict";
  function render(container, fields, values, prefix) {
    container.innerHTML = "";
    fields.filter(function (f) { return f.enabled; }).forEach(function (f) {
      var id = prefix + "-" + f.machine_name;
      var wrap = document.createElement("div");
      wrap.className = "field";
      var label = document.createElement("label");
      label.htmlFor = id;
      label.textContent = f.label + (f.required ? " *" : "");
      wrap.appendChild(label);
      var input;
      var value = values[f.machine_name] == null ? "" : String(values[f.machine_name]);
      if (f.field_type === "select") {
        input = document.createElement("select");
        var empty = document.createElement("option");
        empty.value = ""; empty.textContent = TT.t("misc.choose");
        input.appendChild(empty);
        f.options.forEach(function (opt) {
          var o = document.createElement("option"); o.value = opt; o.textContent = opt;
          if (opt === value) o.selected = true;
          input.appendChild(o);
        });
      } else if (f.field_type === "checkbox") {
        input = document.createElement("input"); input.type = "checkbox"; input.checked = value === "1";
      } else {
        input = document.createElement("input");
        input.type = f.field_type === "number" ? "number" : "text";
        if (f.field_type === "number") { input.step = "any"; input.dir = "ltr"; }
        input.maxLength = 1000; input.value = value;
      }
      input.id = id; input.name = f.machine_name; input.setAttribute("data-cf-name", f.machine_name);
      if (f.required && f.field_type !== "checkbox") input.required = true;
      wrap.appendChild(input);
      container.appendChild(wrap);
    });
  }
  function collect(container) {
    var out = {};
    container.querySelectorAll("[data-cf-name]").forEach(function (el) {
      out[el.getAttribute("data-cf-name")] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
    });
    return out;
  }
  window.TTCustomFields = { render: render, collect: collect };
})();
