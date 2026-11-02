/* SVG chart library. Every function returns an SVG string so the same charts
   render in the console and inside the standalone HTML reports.
   Colors use CSS variables with inline fallbacks (reports have no stylesheet). */
(function () {
  "use strict";

  var PALETTE = ["#0F6CBD", "#2E9D8F", "#C27C0E", "#8764B8", "#D13438", "#5C7080", "#4F9D2D", "#B4009E"];
  var TONES = { ok: "#107C41", warning: "#C27C0E", error: "#C42B1C", skipped: "#8A8886", preview: "#5C7080", running: "#0F6CBD" };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(value, options) {
    return options && options.format ? options.format(value) : String(Math.round(value * 10) / 10);
  }
  function color(i) { return PALETTE[i % PALETTE.length]; }
  function scoreTone(value) { return value >= 80 ? TONES.ok : value >= 60 ? TONES.warning : TONES.error; }
  var TEXT = 'style="fill:var(--chart-text,#55606B)"';
  var GRID = 'style="stroke:var(--chart-grid,#E3E6EA)"';
  var TRACK = "var(--chart-track,#E8EBEF)";

  function svg(width, height, title, body, extra) {
    return '<svg class="chart" viewBox="0 0 ' + width + " " + height + '" width="100%" role="img" preserveAspectRatio="xMidYMid meet" ' +
      'font-family="Segoe UI, system-ui, sans-serif" ' + (extra || "") + '><title>' + esc(title) + "</title>" + body + "</svg>";
  }

  function empty(message, height) {
    return svg(400, height || 160, message, '<text x="200" y="' + ((height || 160) / 2) + '" text-anchor="middle" font-size="13" ' + TEXT + ">" + esc(message) + "</text>");
  }

  /* Semicircular score gauge, 0-100. */
  function gauge(value, options) {
    options = options || {};
    var v = Math.max(0, Math.min(100, Number(value) || 0));
    var cx = 100, cy = 100, r = 80;
    function point(p) {
      var a = Math.PI * (1 - p / 100);
      return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
    }
    var start = point(0), full = point(100);
    var arc = 'd="M' + start[0] + " " + start[1] + " A" + r + " " + r + " 0 0 1 " + full[0] + " " + full[1] + '"';
    var track = "<path " + arc + ' fill="none" stroke-width="16" stroke-linecap="round" style="stroke:' + TRACK + '"/>';
    // pathLength=100 lets the dash length equal the score; the console animates it from 0.
    var bar = v > 0 ? '<path class="gauge-bar" ' + arc + ' pathLength="100" stroke-dasharray="' + v + ' 100" fill="none" stroke="' + scoreTone(v) +
      '" stroke-width="16" stroke-linecap="round"/>' : "";
    var label = '<text x="100" y="92" text-anchor="middle" font-size="38" font-weight="600" style="fill:var(--chart-strong,#1B2733)">' + Math.round(v) + "</text>" +
      '<text x="100" y="116" text-anchor="middle" font-size="12" ' + TEXT + ">/ 100</text>";
    return svg(200, 124, (options.label || "Score") + ": " + Math.round(v) + " of 100", track + bar + label);
  }

  /* Vertical bars: series [{label, value, color?}] */
  function bars(series, options) {
    options = options || {};
    if (!series || !series.length) return empty(options.empty || "No data yet", options.height);
    var width = 520, height = options.height || 200, left = 44, bottom = 34, top = 14;
    var max = Math.max.apply(null, series.map(function (s) { return s.value; }).concat([options.max || 0, 1]));
    var plotH = height - top - bottom, slot = (width - left - 8) / series.length;
    var barW = Math.min(46, slot * 0.62), body = "";
    [0, 0.5, 1].forEach(function (f) {
      var y = top + plotH * (1 - f);
      body += '<line x1="' + left + '" x2="' + (width - 4) + '" y1="' + y + '" y2="' + y + '" ' + GRID + "/>" +
        '<text x="' + (left - 6) + '" y="' + (y + 4) + '" text-anchor="end" font-size="10" ' + TEXT + ">" + esc(fmt(max * f, options)) + "</text>";
    });
    series.forEach(function (s, i) {
      var h = Math.max(s.value > 0 ? 2 : 0, plotH * s.value / max);
      var x = left + slot * i + (slot - barW) / 2, y = top + plotH - h;
      body += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barW.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="3" fill="' +
        (s.color || options.color || color(0)) + '" data-tip="' + esc(s.label + ": " + fmt(s.value, options)) + '"><title>' + esc(s.label + ": " + fmt(s.value, options)) + "</title></rect>" +
        '<text x="' + (x + barW / 2).toFixed(1) + '" y="' + (height - bottom + 16) + '" text-anchor="middle" font-size="10" ' + TEXT + ">" +
        esc(String(s.label).slice(0, 14)) + "</text>";
    });
    return svg(width, height, options.title || "Bar chart", body);
  }

  /* Horizontal bars with labels on the left. */
  function hbars(series, options) {
    options = options || {};
    if (!series || !series.length) return empty(options.empty || "No data yet", options.height);
    var width = 520, row = 30, labelW = 190, top = 6;
    var height = top + series.length * row + 4;
    var max = Math.max.apply(null, series.map(function (s) { return s.value; }).concat([1]));
    var body = "";
    series.forEach(function (s, i) {
      var y = top + i * row, w = Math.max(s.value > 0 ? 2 : 0, (width - labelW - 90) * s.value / max);
      var label = String(s.label);
      body += '<text x="0" y="' + (y + 18) + '" font-size="12" ' + TEXT + ">" + esc(label.length > 30 ? label.slice(0, 29) + "…" : label) + "</text>" +
        '<rect x="' + labelW + '" y="' + (y + 6) + '" width="' + (width - labelW - 90) + '" height="16" rx="3" style="fill:' + TRACK + '"/>' +
        '<rect x="' + labelW + '" y="' + (y + 6) + '" width="' + w.toFixed(1) + '" height="16" rx="3" fill="' + (s.color || color(i)) +
        '" data-tip="' + esc(label + ": " + fmt(s.value, options)) + '"><title>' +
        esc(s.label + ": " + fmt(s.value, options)) + "</title></rect>" +
        '<text x="' + (width - 84) + '" y="' + (y + 18) + '" font-size="12" font-weight="600" style="fill:var(--chart-strong,#1B2733)">' + esc(fmt(s.value, options)) + "</text>";
    });
    return svg(width, height, options.title || "Horizontal bar chart", body);
  }

  /* Donut with optional center text. Pair with Charts.legend(series). */
  function donut(series, options) {
    options = options || {};
    var total = (series || []).reduce(function (a, s) { return a + Math.max(0, s.value); }, 0);
    if (!total) return empty(options.empty || "No data yet", 180);
    var cx = 90, cy = 90, r = 70, inner = 46, angle = -Math.PI / 2, body = "";
    series.forEach(function (s, i) {
      var part = Math.max(0, s.value) / total;
      if (!part) return;
      var c = s.color || color(i);
      if (part >= 0.9999) {
        body += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (r + inner) / 2 + '" fill="none" stroke="' + c + '" stroke-width="' + (r - inner) + '"><title>' + esc(s.label) + "</title></circle>";
        return;
      }
      var a2 = angle + part * Math.PI * 2, large = part > 0.5 ? 1 : 0;
      var p = function (rad, a) { return (cx + rad * Math.cos(a)).toFixed(2) + " " + (cy + rad * Math.sin(a)).toFixed(2); };
      body += '<path d="M' + p(r, angle) + " A" + r + " " + r + " 0 " + large + " 1 " + p(r, a2) + " L" + p(inner, a2) + " A" + inner + " " + inner + " 0 " + large + " 0 " + p(inner, angle) +
        ' Z" fill="' + c + '" stroke="var(--surface,#fff)" stroke-width="1.5" data-tip="' + esc(s.label + ": " + fmt(s.value, options) + " (" + Math.round(part * 100) + "%)") +
        '"><title>' + esc(s.label + ": " + fmt(s.value, options) + " (" + Math.round(part * 100) + "%)") + "</title></path>";
      angle = a2;
    });
    if (options.center != null) {
      body += '<text x="' + cx + '" y="' + (cy + 2) + '" text-anchor="middle" font-size="20" font-weight="600" style="fill:var(--chart-strong,#1B2733)">' + esc(options.center) + "</text>";
      if (options.sub) body += '<text x="' + cx + '" y="' + (cy + 19) + '" text-anchor="middle" font-size="10" ' + TEXT + ">" + esc(options.sub) + "</text>";
    }
    return svg(180, 180, options.title || "Donut chart", body, 'style="max-width:200px"');
  }

  function legend(series, options) {
    var total = (series || []).reduce(function (a, s) { return a + Math.max(0, s.value); }, 0) || 1;
    return '<ul class="legend">' + (series || []).map(function (s, i) {
      return '<li><span class="swatch" style="background:' + (s.color || color(i)) + '"></span><span class="legend-label">' + esc(s.label) +
        '</span><span class="legend-value">' + esc(fmt(s.value, options)) + ' <small>' + Math.round(100 * Math.max(0, s.value) / total) + "%</small></span></li>";
    }).join("") + "</ul>";
  }

  /* Lines over time: series [{name, color?, points:[{x: ISO date, y}]}] */
  function line(series, options) {
    options = options || {};
    var points = [];
    (series || []).forEach(function (s) { (s.points || []).forEach(function (p) { points.push(p); }); });
    if (points.length < 1) return empty(options.empty || "Run a few scans to see the trend", options.height);
    var width = 560, height = options.height || 200, left = 36, right = 10, top = 12, bottom = 28;
    var times = points.map(function (p) { return new Date(p.x).getTime(); });
    var t0 = Math.min.apply(null, times), t1 = Math.max.apply(null, times);
    if (t1 === t0) { t0 -= 3600e3; t1 += 3600e3; }
    var min = options.min != null ? options.min : Math.min.apply(null, points.map(function (p) { return p.y; }));
    var max = options.max != null ? options.max : Math.max.apply(null, points.map(function (p) { return p.y; }));
    if (max === min) max = min + 1;
    var plotW = width - left - right, plotH = height - top - bottom, body = "";
    function X(t) { return left + plotW * (t - t0) / (t1 - t0); }
    function Y(v) { return top + plotH * (1 - (v - min) / (max - min)); }
    [0, 0.5, 1].forEach(function (f) {
      var v = min + (max - min) * f, y = Y(v);
      body += '<line x1="' + left + '" x2="' + (width - right) + '" y1="' + y + '" y2="' + y + '" ' + GRID + "/>" +
        '<text x="' + (left - 6) + '" y="' + (y + 4) + '" text-anchor="end" font-size="10" ' + TEXT + ">" + esc(fmt(v, options)) + "</text>";
    });
    var shortSpan = t1 - t0 < 2 * 86400e3;
    (options.xLabels === false ? [] : [t0, (t0 + t1) / 2, t1]).forEach(function (t, i) {
      var d = new Date(t);
      var label = shortSpan ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
      body += '<text x="' + X(t) + '" y="' + (height - 8) + '" text-anchor="' + ["start", "middle", "end"][i] + '" font-size="10" ' + TEXT + ">" + esc(label) + "</text>";
    });
    (series || []).forEach(function (s, i) {
      var c = s.color || color(i), pts = (s.points || []).map(function (p) { return [X(new Date(p.x).getTime()), Y(p.y), p]; });
      if (!pts.length) return;
      if (pts.length > 1) {
        body += '<polyline fill="none" stroke="' + c + '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" points="' +
          pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ") + '"/>';
      }
      if (options.area && pts.length > 1) {
        body += '<polygon fill="' + c + '" fill-opacity=".12" points="' + pts[0][0].toFixed(1) + "," + (top + plotH) + " " +
          pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ") + " " + pts[pts.length - 1][0].toFixed(1) + "," + (top + plotH) + '"/>';
      }
      if (options.dots === false) return;
      pts.forEach(function (p) {
        var tip = s.name + " · " + new Date(p[2].x).toLocaleString() + ": " + fmt(p[2].y, options);
        body += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3.2" fill="' + c + '" data-tip="' + esc(tip) + '"><title>' + esc(tip) + "</title></circle>";
      });
    });
    return svg(width, height, options.title || "Trend chart", body);
  }

  /* Stacked vertical bars: labels [..], stacks [{name, color, values:[..]}] */
  function stacked(labels, stacks, options) {
    options = options || {};
    if (!labels || !labels.length) return empty(options.empty || "No activity in this period", options.height);
    var width = 560, height = options.height || 200, left = 30, bottom = 28, top = 10;
    var totals = labels.map(function (_, i) { return stacks.reduce(function (a, s) { return a + (s.values[i] || 0); }, 0); });
    var max = Math.max.apply(null, totals.concat([1]));
    var plotH = height - top - bottom, slot = (width - left - 6) / labels.length, barW = Math.max(3, Math.min(30, slot * 0.7)), body = "";
    [0, 1].forEach(function (f) {
      var y = top + plotH * (1 - f);
      body += '<line x1="' + left + '" x2="' + (width - 4) + '" y1="' + y + '" y2="' + y + '" ' + GRID + "/>" +
        '<text x="' + (left - 6) + '" y="' + (y + 4) + '" text-anchor="end" font-size="10" ' + TEXT + ">" + Math.round(max * f) + "</text>";
    });
    var step = Math.ceil(labels.length / 8);
    labels.forEach(function (label, i) {
      var x = left + slot * i + (slot - barW) / 2, y = top + plotH;
      stacks.forEach(function (s) {
        var v = s.values[i] || 0, h = plotH * v / max;
        if (!v) return;
        y -= h;
        body += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barW.toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + s.color +
          '" data-tip="' + esc(label + " · " + s.name + ": " + v) + '"><title>' +
          esc(label + " · " + s.name + ": " + v) + "</title></rect>";
      });
      if (i % step === 0) {
        body += '<text x="' + (x + barW / 2).toFixed(1) + '" y="' + (height - 8) + '" text-anchor="middle" font-size="10" ' + TEXT + ">" + esc(label) + "</text>";
      }
    });
    return svg(width, height, options.title || "Stacked bar chart", body);
  }

  function sparkline(values, options) {
    options = options || {};
    if (!values || values.length < 2) return "";
    var width = 120, height = 32, min = Math.min.apply(null, values), max = Math.max.apply(null, values);
    if (max === min) { max += 1; min -= 1; }
    var pts = values.map(function (v, i) {
      return (2 + (width - 4) * i / (values.length - 1)).toFixed(1) + "," + (2 + (height - 4) * (1 - (v - min) / (max - min))).toFixed(1);
    }).join(" ");
    return '<svg class="sparkline" viewBox="0 0 ' + width + " " + height + '" width="' + width + '" height="' + height + '" aria-hidden="true"><polyline fill="none" stroke="' +
      (options.color || color(0)) + '" stroke-width="2" stroke-linejoin="round" points="' + pts + '"/></svg>';
  }

  /* Calendar heatmap of daily counts: {"YYYY-MM-DD": n}, last `weeks` weeks ending today. */
  function heatmap(counts, options) {
    options = options || {};
    var weeks = options.weeks || 26, cell = 12, gap = 3, left = 26, top = 16;
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var start = new Date(today); start.setDate(start.getDate() - (weeks * 7 - 1) - ((today.getDay() + 6) % 7 === 6 ? 0 : 0));
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));  // align to Monday
    var max = 1, body = "", lastMonth = -1;
    Object.keys(counts || {}).forEach(function (k) { max = Math.max(max, counts[k]); });
    var shades = ["var(--chart-track,#E8ECF1)", "#B7D7F2", "#7FB6E6", "#3F8FD4", "#0F6CBD"];
    for (var d = new Date(start), i = 0; d <= today; d.setDate(d.getDate() + 1), i++) {
      var week = Math.floor(i / 7), dow = (d.getDay() + 6) % 7;
      var key = d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
      var n = counts[key] || 0, level = n ? Math.min(4, 1 + Math.floor(3 * n / max)) : 0;
      var x = left + week * (cell + gap), y = top + dow * (cell + gap);
      if (d.getMonth() !== lastMonth && dow === 0) {
        lastMonth = d.getMonth();
        body += '<text x="' + x + '" y="10" font-size="10" ' + TEXT + ">" + esc(d.toLocaleDateString(undefined, { month: "short" })) + "</text>";
      }
      var tip = d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) + ": " + n + (n === 1 ? " run" : " runs");
      body += '<rect x="' + x + '" y="' + y + '" width="' + cell + '" height="' + cell + '" rx="2.5" style="fill:' + shades[level] + '" data-tip="' + esc(tip) + '"><title>' + esc(tip) + "</title></rect>";
    }
    ["Mon", "Wed", "Fri"].forEach(function (label, i) {
      body += '<text x="0" y="' + (top + (i * 2) * (cell + gap) + 10) + '" font-size="9.5" ' + TEXT + ">" + label + "</text>";
    });
    var width = left + (weeks + 1) * (cell + gap), height = top + 7 * (cell + gap);
    return svg(width, height, options.title || "Activity calendar", body, 'class="chart heatmap"') +
      '<div class="heat-legend">Less' + shades.map(function (s) { return '<i style="background:' + s + '"></i>'; }).join("") + "More</div>";
  }

  /* Compact live area chart for 0..max values (no axes). */
  function live(values, options) {
    options = options || {};
    var width = 300, height = 64, n = Math.max(values.length, 2), max = options.max || Math.max.apply(null, values.concat([1]));
    if (!values.length) return svg(width, height, "No data", "", 'preserveAspectRatio="none"');
    var pts = values.map(function (v, i) {
      return [(width * i / (n - 1)), height - 2 - (height - 4) * Math.min(1, v / max)];
    });
    var c = options.color || color(0);
    var line = pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
    return '<svg viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<polygon fill="' + c + '" fill-opacity=".14" points="0,' + height + " " + line + " " + pts[pts.length - 1][0].toFixed(1) + "," + height + '"/>' +
      '<polyline fill="none" stroke="' + c + '" stroke-width="2" vector-effect="non-scaling-stroke" points="' + line + '"/></svg>';
  }

  window.Charts = {
    PALETTE: PALETTE, TONES: TONES, color: color, scoreTone: scoreTone,
    gauge: gauge, bars: bars, hbars: hbars, donut: donut, legend: legend, line: line, stacked: stacked, sparkline: sparkline, empty: empty,
    heatmap: heatmap, live: live
  };
})();
