/* Animations: three levels chosen in Settings › Appearance.
   fun     page entrances, hover effects, ripples, confetti when work completes (default)
   subtle  only short fades for dialogs, panels and toasts
   off     nothing moves except what shows that work is running (spinners, progress bars)
   The level lives on <html data-fx>, set before the first paint by index.html. */
(function () {
  "use strict";
  var LEVELS = ["fun", "subtle", "off"];
  var COLORS = ["#2563EB", "#0E9F6E", "#D97706", "#7C3AED", "#DB2777", "#0891B2", "#F59E0B"];

  function stored() {
    try { return JSON.parse(localStorage.getItem("wmm.animations") || "null"); } catch (e) { return null; }
  }
  /* Without a choice, the Windows setting "Animation effects" off means subtle. */
  function level() {
    var v = stored();
    if (LEVELS.indexOf(v) >= 0) return v;
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "subtle" : "fun";
  }
  function apply() { document.documentElement.setAttribute("data-fx", level()); }
  function set(value) {
    if (LEVELS.indexOf(value) < 0) return;
    try { localStorage.setItem("wmm.animations", JSON.stringify(value)); } catch (e) { /* storage unavailable */ }
    apply();
    if (value === "fun") confetti({ count: 60 });
  }
  function fun() { return level() === "fun"; }

  /* Confetti from the top of the window (or from an element), on a canvas that removes itself. */
  function confetti(options) {
    if (!fun()) return;
    options = options || {};
    var canvas = document.createElement("canvas"), ctx = canvas.getContext("2d");
    if (!ctx) return;
    var dpr = window.devicePixelRatio || 1, w = window.innerWidth, h = window.innerHeight;
    canvas.className = "fx-canvas";
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);
    document.body.appendChild(canvas);
    var origin = options.from ? options.from.getBoundingClientRect() : null;
    var ox = origin ? origin.left + origin.width / 2 : w / 2, oy = origin ? origin.top + origin.height / 2 : -10;
    var parts = [];
    for (var i = 0; i < (options.count || 140); i++) {
      var angle = origin ? Math.random() * Math.PI * 2 : Math.PI / 2 + (Math.random() - 0.5) * 1.6;
      var speed = origin ? 3 + Math.random() * 6 : 4 + Math.random() * 7;
      parts.push({
        x: origin ? ox : Math.random() * w, y: oy, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - (origin ? 3 : 0),
        size: 5 + Math.random() * 6, rot: Math.random() * 6.28, spin: (Math.random() - 0.5) * 0.3,
        color: COLORS[i % COLORS.length], shape: i % 3
      });
    }
    var start = performance.now(), duration = options.duration || 2600;
    (function frame(now) {
      var t = now - start;
      ctx.clearRect(0, 0, w, h);
      parts.forEach(function (p) {
        p.vy += 0.16;          // gravity
        p.vx *= 0.99;          // air
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.spin;
        ctx.save();
        ctx.globalAlpha = Math.max(0, 1 - t / duration);
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        if (p.shape === 0) ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
        else if (p.shape === 1) { ctx.beginPath(); ctx.arc(0, 0, p.size / 3, 0, 6.28); ctx.fill(); }
        else { ctx.beginPath(); ctx.moveTo(0, -p.size / 2); ctx.lineTo(p.size / 2, p.size / 2); ctx.lineTo(-p.size / 2, p.size / 2); ctx.fill(); }
        ctx.restore();
      });
      if (t < duration) requestAnimationFrame(frame); else canvas.remove();
    })(start);
  }

  /* A small burst of sparks around an element (favorites, completed checklists). */
  function burst(el) {
    if (!fun() || !el) return;
    var r = el.getBoundingClientRect();
    for (var i = 0; i < 10; i++) {
      var s = document.createElement("span");
      s.className = "fx-spark";
      var a = (i / 10) * Math.PI * 2, d = 22 + Math.random() * 14;
      s.style.left = r.left + r.width / 2 + "px";
      s.style.top = r.top + r.height / 2 + "px";
      s.style.background = COLORS[i % COLORS.length];
      s.style.setProperty("--dx", Math.cos(a) * d + "px");
      s.style.setProperty("--dy", Math.sin(a) * d + "px");
      document.body.appendChild(s);
      setTimeout(s.remove.bind(s), 700);
    }
  }

  /* Cards and sections of a new page arrive one after the other. */
  function pageEnter(content) {
    if (!fun()) return;
    content.classList.remove("fx-enter");
    void content.offsetWidth;  // restart the animation on the same element
    content.classList.add("fx-enter");
    setTimeout(function () { content.classList.remove("fx-enter"); }, 1200);
  }

  /* Ripple from the click point on buttons and tiles. */
  document.addEventListener("pointerdown", function (e) {
    if (!fun() || e.button !== 0) return;
    // Not on navigation items and icon buttons: their indicator and badge sit outside their box.
    var target = e.target.closest && e.target.closest(".btn, .quick, .start-card, .tile");
    if (!target || target.disabled) return;
    var r = target.getBoundingClientRect(), size = Math.max(r.width, r.height) * 2;
    var wave = document.createElement("span");
    wave.className = "fx-ripple";
    wave.style.width = wave.style.height = size + "px";
    wave.style.left = e.clientX - r.left - size / 2 + "px";
    wave.style.top = e.clientY - r.top - size / 2 + "px";
    target.appendChild(wave);
    setTimeout(wave.remove.bind(wave), 650);
  });

  /* The logo spins when clicked: a small reward for the curious. */
  document.addEventListener("click", function (e) {
    var logo = e.target.closest && e.target.closest(".brand svg");
    if (!logo || !fun()) return;
    logo.classList.remove("fx-spin");
    void logo.getBoundingClientRect();
    logo.classList.add("fx-spin");
  });

  if (window.matchMedia) {
    var media = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (media.addEventListener) media.addEventListener("change", apply);
  }
  apply();

  window.FX = { level: level, set: set, fun: fun, confetti: confetti, burst: burst, pageEnter: pageEnter, LEVELS: LEVELS };
})();
