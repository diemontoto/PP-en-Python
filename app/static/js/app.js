/* Comportamiento de la interfaz (sin dependencias, compatible con CSP script-src 'self'). */
(function () {
  "use strict";
  var body = document.body;

  // Menú lateral en celulares / tablets
  var toggle = document.getElementById("menu-toggle");
  var scrim = document.getElementById("scrim");
  if (toggle) toggle.addEventListener("click", function () { body.classList.toggle("nav-open"); });
  if (scrim) scrim.addEventListener("click", function () { body.classList.remove("nav-open"); });

  // Confirmación antes de enviar formularios con data-confirm
  document.addEventListener("submit", function (ev) {
    var msg = ev.target.getAttribute && ev.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) ev.preventDefault();
  });

  // Filtro de texto para listas de casillas: <input data-filter-list="#id">
  document.querySelectorAll("[data-filter-list]").forEach(function (input) {
    var list = document.querySelector(input.getAttribute("data-filter-list"));
    if (!list) return;
    input.addEventListener("input", function () {
      var t = input.value.toLowerCase();
      list.querySelectorAll("label").forEach(function (l) {
        l.classList.toggle("hidden", t && l.textContent.toLowerCase().indexOf(t) === -1);
      });
    });
  });

  // Seleccionar / desmarcar todas las casillas visibles: <button data-check-all="#id" data-state="1|0">
  document.querySelectorAll("[data-check-all]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var list = document.querySelector(btn.getAttribute("data-check-all"));
      var on = btn.getAttribute("data-state") === "1";
      if (list) list.querySelectorAll("label:not(.hidden) input[type=checkbox]").forEach(function (c) { c.checked = on; });
    });
  });

  // Select dependiente: mostrar sólo opciones cuyo data-<attr> coincide con el select padre.
  // <select data-depends-on="#f_empresa_id" data-depends-attr="data-empresa">
  document.querySelectorAll("select[data-depends-on]").forEach(function (child) {
    var parent = document.querySelector(child.getAttribute("data-depends-on"));
    var attr = child.getAttribute("data-depends-attr");
    if (!parent) return;
    function apply() {
      var val = parent.value;
      Array.prototype.forEach.call(child.options, function (o) {
        if (!o.value) { o.hidden = false; return; }
        var ok = !val || o.getAttribute(attr) === val;
        o.hidden = !ok; o.disabled = !ok;
        if (!ok && o.selected) child.value = "";
      });
    }
    parent.addEventListener("change", apply);
    apply();
  });

  // Rellenar horas requeridas al elegir especialidad: <select data-fill-target="#id" data-fill-attr="data-horas">
  document.querySelectorAll("select[data-fill-target]").forEach(function (sel) {
    var target = document.querySelector(sel.getAttribute("data-fill-target"));
    var attr = sel.getAttribute("data-fill-attr");
    if (!target) return;
    sel.addEventListener("change", function () {
      var o = sel.options[sel.selectedIndex];
      var v = o && o.getAttribute(attr);
      if (v && !target.dataset.touched) target.value = v;
    });
    target.addEventListener("input", function () { target.dataset.touched = "1"; });
  });

  // Autoenvío de filtros: <select data-autosubmit>
  document.querySelectorAll("select[data-autosubmit]").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });
})();
