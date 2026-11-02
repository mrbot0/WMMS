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

  function moving() { return level() !== "off"; }

  /* ---------- scroll reveal: what is below the fold arrives when it scrolls into view ---------- */
  var REVEAL = ".card, .kpi, .section-title, .tile, .hub-page, .hub-card, .action-card, .rec, .page-pager, .guide-tip";
  var observer = window.IntersectionObserver ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add("fx-in");
      observer.unobserve(e.target);
    });
  }, { root: document.getElementById("scroller"), rootMargin: "0px 0px -40px 0px", threshold: 0.08 }) : null;
  function reveal(root) {
    if (!observer || !moving() || !root) return;
    var limit = window.innerHeight;
    Array.prototype.forEach.call(root.querySelectorAll(REVEAL), function (el, i) {
      if (el.closest(".modal") || (el.parentElement && el.parentElement.closest(".fx-reveal"))) return;  // nested items ride on their parent
      if (el.getBoundingClientRect().top < limit) return;  // already visible: the page entrance handles it
      el.classList.add("fx-reveal");
      el.style.setProperty("--fx-delay", (i % 4) * 60 + "ms");
      observer.observe(el);
    });
  }

  /* ---------- pointer effects: spotlight on cards, tilt on tiles, magnetic primary buttons ---------- */
  var SPOT = ".card, .kpi, .hub-page, .hub-card, .action-card, .tile, .quick, .live-card";
  var TILT = ".hub-page, .kpi, .tile, .quick";
  var pending = null, lastTilt = null, lastMagnet = null;
  document.addEventListener("pointermove", function (e) {
    if (pending || e.pointerType === "touch") return;
    pending = requestAnimationFrame(function () {
      pending = null;
      if (!fun()) return;
      var t = e.target && e.target.closest ? e.target : null;
      var spot = t && t.closest(SPOT);
      if (spot) {
        var r = spot.getBoundingClientRect();
        spot.style.setProperty("--mx", e.clientX - r.left + "px");
        spot.style.setProperty("--my", e.clientY - r.top + "px");
      }
      var tilt = t && t.closest(TILT);
      if (lastTilt && lastTilt !== tilt) lastTilt.style.transform = "";
      if (tilt) {
        var b = tilt.getBoundingClientRect(), px = (e.clientX - b.left) / b.width - 0.5, py = (e.clientY - b.top) / b.height - 0.5;
        tilt.style.transform = "perspective(700px) rotateX(" + (-py * 5).toFixed(2) + "deg) rotateY(" + (px * 6).toFixed(2) + "deg) translateY(-3px)";
      }
      lastTilt = tilt;
      var magnet = t && t.closest(".btn-primary:not(:disabled), #btn-scan");
      if (lastMagnet && lastMagnet !== magnet) lastMagnet.style.transform = "";
      if (magnet) {
        var m = magnet.getBoundingClientRect();
        magnet.style.transform = "translate(" + ((e.clientX - m.left - m.width / 2) * 0.12).toFixed(1) + "px," + ((e.clientY - m.top - m.height / 2) * 0.18).toFixed(1) + "px)";
      }
      lastMagnet = magnet;
    });
  }, { passive: true });
  document.documentElement.addEventListener("pointerleave", function () {
    if (lastTilt) lastTilt.style.transform = "";
    if (lastMagnet) lastMagnet.style.transform = "";
    lastTilt = lastMagnet = null;
  });

  /* ---------- sidebar: an indicator glides to the active page ---------- */
  var pillTop = null;
  function navPill() {
    var nav = document.getElementById("nav");
    if (!nav) return;
    var active = nav.querySelector(".nav-item.active");
    var pill = nav.querySelector(".nav-pill") || nav.insertBefore(document.createElement("span"), nav.firstChild);
    pill.className = "nav-pill";
    pill.setAttribute("aria-hidden", "true");
    if (!active) { pill.style.opacity = "0"; return; }
    var top = active.offsetTop, height = active.offsetHeight;
    pill.style.height = height + "px";
    pill.style.opacity = "1";
    pill.style.transition = "none";
    pill.style.transform = "translateY(" + (pillTop == null || !moving() ? top : pillTop) + "px)";
    if (pillTop != null && moving() && pillTop !== top) {
      void pill.offsetWidth;
      pill.style.transition = "";
      pill.style.transform = "translateY(" + top + "px)";
    }
    pillTop = top;
  }

  /* ---------- theme switch: the new theme spreads in a circle from the click ---------- */
  function themeSwitch(change, event) {
    if (!document.startViewTransition || !fun()) { change(); return; }
    var x = event && event.clientX ? event.clientX : window.innerWidth - 80, y = event && event.clientY ? event.clientY : 40;
    var radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    var transition = document.startViewTransition(change);
    transition.ready.then(function () {
      document.documentElement.animate({ clipPath: ["circle(0px at " + x + "px " + y + "px)", "circle(" + radius + "px at " + x + "px " + y + "px)"] },
        { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" });
    }).catch(function () { /* the theme still changed */ });
  }

  /* ---------- floating text: "+5" rising from an element ---------- */
  function floatText(el, text, tone) {
    if (!fun() || !el) return;
    var r = el.getBoundingClientRect(), f = document.createElement("span");
    f.className = "fx-float-text" + (tone ? " " + tone : "");
    f.textContent = text;
    f.style.left = r.left + r.width / 2 + "px";
    f.style.top = r.top + "px";
    document.body.appendChild(f);
    setTimeout(f.remove.bind(f), 1400);
  }

  /* ---------- scroll: top bar shadow, back-to-top progress ring ---------- */
  var scroller = document.getElementById("scroller");
  if (scroller) {
    var ticking = false;
    scroller.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        var max = scroller.scrollHeight - scroller.clientHeight, p = max > 0 ? scroller.scrollTop / max : 0;
        var bar = document.querySelector(".topbar");
        if (bar) bar.classList.toggle("scrolled", scroller.scrollTop > 6);
        var top = document.getElementById("to-top");
        if (top) top.style.setProperty("--p", Math.round(p * 100) + "%");
      });
    }, { passive: true });
  }

  /* ---------- "Run" launches the card it belongs to ---------- */
  document.addEventListener("click", function (e) {
    var run = e.target.closest && e.target.closest("[data-run], [data-run-reports], #tb-run, #pick-run");
    if (!run || !fun()) return;
    var card = run.closest(".action-card, .rec, .quick") || run;
    card.classList.remove("fx-launch");
    void card.offsetWidth;
    card.classList.add("fx-launch");
    setTimeout(function () { card.classList.remove("fx-launch"); }, 900);
  });

  /* ---------- a secret: ↑ ↑ ↓ ↓ ← → ← → B A starts a party ---------- */
  var SECRET = ["arrowup", "arrowup", "arrowdown", "arrowdown", "arrowleft", "arrowright", "arrowleft", "arrowright", "b", "a"], typed = 0;
  document.addEventListener("keydown", function (e) {
    var key = (e.key || "").toLowerCase();
    typed = key === SECRET[typed] ? typed + 1 : (key === SECRET[0] ? 1 : 0);
    if (typed < SECRET.length) return;
    typed = 0;
    if (!moving()) return;
    document.documentElement.classList.add("fx-party");
    [0, 500, 1000].forEach(function (d) { setTimeout(function () { confetti({ count: 120 }); }, d); });
    setTimeout(function () { document.documentElement.classList.remove("fx-party"); }, 4200);
  });

  /* First paint: the sidebar items arrive one after the other. */
  if (fun()) {
    document.body.classList.add("fx-boot");
    setTimeout(function () { document.body.classList.remove("fx-boot"); }, 1600);
  }

  if (window.matchMedia) {
    var media = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (media.addEventListener) media.addEventListener("change", apply);
  }
  apply();

  window.FX = { level: level, set: set, fun: fun, moving: moving, confetti: confetti, burst: burst, pageEnter: pageEnter, reveal: reveal, navPill: navPill,
    themeSwitch: themeSwitch, floatText: floatText, LEVELS: LEVELS };
})();
