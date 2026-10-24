/* SystemOne Extract Index: leaderboard page.
   Everything score-like on this page comes from data/board.json. */
(function () {
  'use strict';

  var BOARD_URL = 'data/board.json';
  var TYPE_ORDER = ['text', 'number', 'date', 'time', 'datetime', 'duration', 'list'];
  // Highlighter colours come from the stylesheet tokens; one colour per area, used everywhere.
  var rootStyle = window.getComputedStyle(document.documentElement);
  function token(name, fallback) {
    var v = rootStyle.getPropertyValue(name);
    return v && v.trim() ? v.trim() : fallback;
  }
  var HL = {
    yellow: token('--hl-yellow', '#FFD21E'),
    orange: token('--hl-orange', '#FF9D00'),
    mint: token('--hl-mint', '#4ED9A0'),
    sky: token('--hl-sky', '#52C4F7'),
    pink: token('--hl-pink', '#FF7EB6')
  };
  var AREA_COLOURS = { Spans: HL.mint, Documents: HL.orange, Numbers: HL.sky, Entities: HL.pink };
  var AREA_STICKERS = { Spans: 'area-spans', Documents: 'area-documents', Numbers: 'area-numbers', Entities: 'area-entities' };
  var PALETTE = [HL.mint, HL.orange, HL.sky, HL.pink, HL.yellow];

  var state = {
    board: null,
    groups: null,
    metric: 'index',
    sort: { key: 'index', dir: 'desc' },
    open: {}
  };

  /* ---------- helpers ---------- */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function clamp(v) { return Math.max(0, Math.min(100, v)); }
  function fmtScore(v) { return isNum(v) ? v.toFixed(1) : '—'; }
  function fmtInt(v) { return isNum(v) ? Math.round(v).toLocaleString('en-US') : '—'; }
  function fmtMs(v) { return isNum(v) ? Math.round(v).toLocaleString('en-US') : '—'; }
  function fmtShare(v) { return isNum(v) ? Math.round(v * 100) + '%' : '—'; }  // 0-1 shares
  function fmtPct(v) { return isNum(v) ? Math.round(v) + '%' : '—'; }  // 0-100 scores
  function fmtDate(s) {
    if (!s) return '—';
    var m = String(s).match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : String(s);
  }
  function safeUrl(u) { return (typeof u === 'string' && /^https?:\/\//i.test(u)) ? u : null; }
  function safeRel(p) { return (typeof p === 'string' && /^(?!\.\.)(?![a-z]+:)[^\s"'<>]+$/i.test(p)) ? p : null; }
  function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return u; } }
  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''); }
  function plural(n, word) { return fmtInt(n) + ' ' + word + (n === 1 ? '' : 's'); }
  function setText(sel, text) { $all(sel).forEach(function (el) { el.textContent = text; }); }
  function sortDesc(get) {
    return function (a, b) {
      var va = get(a), vb = get(b);
      if (va !== vb) return vb - va;
      return a._i - b._i;
    };
  }

  function areaColour(a) {
    if (AREA_COLOURS[a]) return AREA_COLOURS[a];
    var i = ((state.board && state.board.areas) || []).indexOf(a);
    return PALETTE[(i < 0 ? 0 : i) % PALETTE.length];
  }
  function metricOf(e, m) {
    if (m === 'index') return e.index;
    return e.areas ? e.areas[m.slice(5)] : null;
  }
  function metricLabel(m) { return m === 'index' ? 'Index' : m.slice(5); }

  function initials(e) {
    var s = String(e.org || e.name || '?').trim();
    var parts = s.split(/\s+/);
    return (parts.length > 1 ? parts[0].charAt(0) + parts[1].charAt(0) : s.slice(0, 2)).toUpperCase();
  }
  function avatarHtml(e, cls, fallback) {
    var src = safeRel(e.avatar);
    cls = 'avatar' + (cls ? ' ' + cls : '');
    if (src) return '<img class="' + cls + '" src="' + esc(src) + '" alt="" width="28" height="28" loading="lazy">';
    if (fallback === false) return '';
    return '<span class="' + cls + '" aria-hidden="true">' + esc(initials(e)) + '</span>';
  }
  function kindClass(e) {
    if (e.system === 'two') return 'k-two';
    if (e.system === 'baseline') return 'k-base';
    return e.kind === 'api' ? 'k-api' : 'k-open';
  }
  function kindPill(e) {
    if (e.system === 'baseline') return '<span class="tag k-base">floor</span>';
    var k = e.kind === 'open' ? '<span class="tag k-open">open weights</span>'
      : e.kind === 'api' ? '<span class="tag k-api">api</span>'
      : e.kind ? '<span class="tag">' + esc(e.kind) + '</span>' : '';
    if (e.system === 'two') k += '<span class="tag k-two">system two, reference</span>';
    return k;
  }
  function stickerHtml(area, size) {
    var f = AREA_STICKERS[area];
    if (!f) return '';
    return '<img src="assets/art/' + f + '.webp" width="' + size + '" height="' + size + '" alt="" loading="lazy">';
  }

  /* ---------- JSON examples ---------- */

  function highlightJson(src) {
    var re = /("(?:[^"\\]|\\.)*")(\s*:)?|\bnull\b|\b(?:true|false)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
    var out = '', last = 0, m;
    while ((m = re.exec(src))) {
      out += esc(src.slice(last, m.index));
      var tok = m[0];
      if (m[1]) {
        out += m[2]
          ? '<span class="j-key">' + esc(m[1]) + '</span>' + esc(m[2])
          : '<span class="j-str">' + esc(m[1]) + '</span>';
      } else if (tok === 'null') {
        out += '<span class="j-null">null</span>';
      } else {
        out += '<span class="j-num">' + esc(tok) + '</span>';
      }
      last = m.index + tok.length;
    }
    out += esc(src.slice(last));
    return out;
  }
  function renderJsonExamples() {
    $all('code[data-json]').forEach(function (el) { el.innerHTML = highlightJson(el.textContent); });
  }

  /* ---------- entries ---------- */

  function prepareEntries(board) {
    var entries = (board.entries || []).map(function (e, i) {
      var copy = Object.assign({}, e);
      copy._i = i;
      copy._id = 'entry-' + (slug(e.id || ((e.org || '') + ' ' + (e.name || i))) || i);
      return copy;
    });
    var seen = {};
    entries.forEach(function (e) {
      if (seen[e._id]) { seen[e._id] += 1; e._id += '-' + seen[e._id]; } else { seen[e._id] = 1; }
    });
    var one = entries.filter(function (e) { return e.system !== 'two' && e.system !== 'baseline'; });
    var two = entries.filter(function (e) { return e.system === 'two'; });
    var base = entries.filter(function (e) { return e.system === 'baseline'; });
    var ranked = one.filter(function (e) { return isNum(e.index); }).sort(sortDesc(function (e) { return e.index; }));
    var rank = 0;
    ranked.forEach(function (e, i) {
      if (i === 0 || e.index < ranked[i - 1].index) rank = i + 1;
      e._rank = rank;
    });
    return { one: one, two: two, base: base, floor: base[0] || null, ranked: ranked, all: entries };
  }

  /* ---------- legend and switch ---------- */

  function renderLegend() {
    var g = state.groups, items = [];
    items.push('<span><i></i>Open weights</span>');
    items.push('<span><i class="hatch"></i>API</span>');
    if (g.two.length) items.push('<span><i class="ref"></i>System Two, reference</span>');
    if (g.floor) {
      var fv = metricOf(g.floor, state.metric);
      items.push('<span><i class="floor"></i>Floor' + (isNum(fv) ? ' ' + fv.toFixed(1) : '') + ': answer null everywhere</span>');
    }
    $('[data-legend]').innerHTML = items.join('');
  }

  function renderSwitch() {
    var areas = state.board.areas || [];
    var opts = [{ key: 'index', label: 'Index' }].concat(areas.map(function (a) {
      return { key: 'area:' + a, label: a, c: areaColour(a) };
    }));
    $('[data-switch]').innerHTML = opts.map(function (o) {
      return '<button type="button" data-metric="' + esc(o.key) + '" aria-pressed="' + (state.metric === o.key) + '"' +
        (o.c ? ' style="--c:' + o.c + '"' : '') + '>' + (o.c ? '<i aria-hidden="true"></i>' : '') + esc(o.label) + '</button>';
    }).join('');
  }

  /* ---------- ranking chart ---------- */

  function renderRanking() {
    var host = $('#ranking'), g = state.groups, m = state.metric;
    host.setAttribute('aria-busy', 'false');
    if (!g.all.length) {
      host.innerHTML = '<div class="empty"><h3>No runs yet</h3><p>Scored runs appear here once they are merged. To add yours, see <a href="#submit">Submit a run</a>.</p></div>';
      return;
    }
    var colour = m === 'index' ? null : areaColour(m.slice(5));
    var get = function (e) { return metricOf(e, m); };
    var ones = g.one.filter(function (e) { return isNum(get(e)); }).sort(sortDesc(get));
    var twos = g.two.filter(function (e) { return isNum(get(e)); }).sort(sortDesc(get));
    var incomplete = g.one.length - ones.length;
    var floorV = g.floor ? get(g.floor) : null;
    var ranks = {}, r = 0;
    ones.forEach(function (e, i) {
      if (i === 0 || get(e) < get(ones[i - 1])) r = i + 1;
      ranks[e._id] = r;
    });

    var n = ones.length + twos.length;

    // One ruled line per run: margin number, avatar, name, then a highlighter stroke whose length is the score.
    function line(e, isTwo) {
      var v = get(e), w = clamp(v) / 100;
      var cls = 'stroke ' + (isTwo ? 'k-two' : (colour ? 'k-area' : kindClass(e)));
      var style = '--v:' + w.toFixed(4) + (colour ? ';--c:' + colour : '');
      var no = isTwo ? '<span class="ln-no ref">ref</span>' : '<span class="ln-no">' + ranks[e._id] + '.</span>';
      return '<li' + (isTwo ? ' class="two"' : '') + '>' + no + avatarHtml(e) +
        '<span class="ln-who"><b>' + esc(e.name || 'Unnamed') + '</b><small>' + esc(e.org || '') + '</small></span>' +
        '<button type="button" class="' + cls + '" style="' + style + '" data-id="' + e._id + '" data-tip-id="' + e._id + '"' +
        ' aria-label="' + esc(e.name) + ', ' + metricLabel(m) + ' ' + v.toFixed(1) + '. Open the row in the table">' +
        '<i aria-hidden="true"></i><span class="tag">' + v.toFixed(1) + '</span></button></li>';
    }
    var axis = '<div class="ruled-axis" aria-hidden="true">' + [0, 25, 50, 75, 100].map(function (v) {
      return '<span style="left:' + v + '%">' + v + '</span>';
    }).join('') + '</div>';
    var grid = [25, 50, 75, 100].map(function (v) { return '<div class="ruled-grid" style="--x:' + (v / 100) + '" aria-hidden="true"></div>'; }).join('');
    var floor = '';
    if (isNum(floorV)) {
      var f = (clamp(floorV) / 100).toFixed(4);
      floor = '<div class="ruled-floor" style="--f:' + f + '" aria-hidden="true"></div>' +
        '<div class="ruled-floor-lab' + (floorV > 62 ? ' flip' : '') + '" style="--f:' + f + '" aria-hidden="true">floor ' + floorV.toFixed(1) + ': answer null everywhere</div>';
    }
    var list = '<ol>' + ones.map(function (e) { return line(e, false); }).join('') + '</ol>';
    if (twos.length) {
      list += '<p class="ruled-sep">System Two, reference: generating models, not ranked</p>' +
        '<ol>' + twos.map(function (e) { return line(e, true); }).join('') + '</ol>';
    }
    var note = '';
    if (n < 4) {
      note = '<p class="ruled-note hand">' +
        (n ? plural(n, 'listed run') + ' so far.' : 'No complete runs yet.') +
        ' Runs are added by pull request; <a href="#submit">submit yours</a>.</p>';
    }
    var incompleteNote = incomplete
      ? '<p class="ruled-incomplete">' + plural(incomplete, 'incomplete run') + ' without ' + (m === 'index' ? 'an' : 'a') + ' ' + esc(metricLabel(m)) + ' score: see the table.</p>'
      : '';
    host.innerHTML =
      '<div class="ruled' + (isNum(floorV) ? ' has-floor' : '') + '" role="group" aria-label="Ranking by ' + esc(metricLabel(m)) + '">' +
        axis + grid + floor + list +
      '</div>' + note + incompleteNote;
  }

  /* ---------- by area ---------- */

  function renderAreas() {
    var host = $('[data-area-chart]'), g = state.groups, board = state.board;
    var areas = board.areas || [], tests = board.tests || [];
    if (!areas.length || !g.all.length) { host.innerHTML = '<p class="empty">No runs yet.</p>'; return; }
    var cols = areas.map(function (a) {
      var c = areaColour(a);
      var nTests = tests.filter(function (t) { return t.area === a; }).length;
      var rows = g.one.concat(g.two).filter(function (e) { return e.areas && isNum(e.areas[a]); })
        .sort(sortDesc(function (e) { return e.areas[a]; }));
      var floorV = g.floor && g.floor.areas ? g.floor.areas[a] : null;
      var items = rows.map(function (e) {
        var v = e.areas[a];
        return '<li class="hb' + (e.system === 'two' ? ' two' : '') + '">' +
          '<span class="hb-name">' + avatarHtml(e, 'sm', false) + '<span>' + esc(e.name) + '</span>' +
          (e.system === 'two' ? '<small>ref</small>' : '') + '</span>' +
          '<span class="hb-track" data-tip-id="' + e._id + '" data-tip-extra="' + esc(a) + ': ' + v.toFixed(1) + '"><i style="width:' + clamp(v) + '%"></i>' +
          (isNum(floorV) ? '<u style="left:' + clamp(floorV) + '%"></u>' : '') + '</span>' +
          '<span class="hb-val">' + v.toFixed(1) + '</span></li>';
      }).join('') || '<li class="hb na"><span class="hb-name muted">No complete runs</span></li>';
      return '<div class="area-col" style="--c:' + c + '"><h4>' + stickerHtml(a, 28) + esc(a) +
        '<small>' + plural(nTests, 'test') + (isNum(floorV) ? ', floor ' + floorV.toFixed(1) : '') + '</small></h4><ol>' + items + '</ol></div>';
    });
    host.innerHTML = '<div class="scroll"><div class="areas">' + cols.join('') + '</div></div>';
  }

  /* ---------- field types ---------- */

  var HATCH_DEF = '<defs><pattern id="hatch-svg" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">' +
    '<rect width="6" height="6" style="fill:' + HL.yellow + ';fill-opacity:.35"/><rect width="3" height="6" style="fill:' + HL.yellow + '"/></pattern></defs>';

  function dotClass(e) {
    return 'dab' + (e.system === 'two' ? ' two' : (e.kind === 'api' ? ' api' : ''));
  }
  function chipSvg(text, x, cy, anchorEnd) {
    var w = Math.round(text.length * 6.7 + 12), h = 18;
    var bx = anchorEnd ? x - w : x;
    return '<rect class="chip-box" x="' + bx + '" y="' + (cy - h / 2) + '" width="' + w + '" height="' + h + '" rx="4"/>' +
      '<text class="chip-text" x="' + (bx + w / 2) + '" y="' + (cy + 4) + '" text-anchor="middle">' + esc(text) + '</text>';
  }

  function renderTypes() {
    var host = $('[data-types-chart]'), g = state.groups;
    var entries = g.two.concat(g.one.slice().reverse()).filter(function (e) { return e.types; });
    var keys = {};
    entries.concat(g.floor ? [g.floor] : []).forEach(function (e) {
      Object.keys(e.types || {}).forEach(function (t) { if (isNum(e.types[t])) keys[t] = true; });
    });
    var types = TYPE_ORDER.filter(function (t) { return keys[t]; })
      .concat(Object.keys(keys).filter(function (t) { return TYPE_ORDER.indexOf(t) < 0; }).sort());
    if (!types.length) { host.innerHTML = '<p class="empty">Not reported yet.</p>'; return; }

    var W = Math.max(300, host.clientWidth || 480), left = 88, right = 18, top = 26, rowH = 32, H = top + types.length * rowH + 4;
    var x = function (v) { return left + (W - left - right) * clamp(v) / 100; };
    var parts = [HATCH_DEF];
    [0, 25, 50, 75, 100].forEach(function (v) {
      parts.push('<line class="ax" x1="' + x(v) + '" y1="' + (top - 4) + '" x2="' + x(v) + '" y2="' + (H - 4) + '"/>');
      parts.push('<text class="tick" x="' + x(v) + '" y="' + (top - 10) + '" text-anchor="middle">' + v + '</text>');
    });
    var top1 = g.ranked[0];
    types.forEach(function (t, i) {
      var cy = top + i * rowH + rowH / 2;
      parts.push(chipSvg(t, left - 10, cy, true));
      parts.push('<line class="ax" x1="' + left + '" y1="' + (cy + rowH / 2) + '" x2="' + x(100) + '" y2="' + (cy + rowH / 2) + '"/>');
      var fv = g.floor && g.floor.types ? g.floor.types[t] : null;
      if (isNum(fv)) {
        parts.push('<line class="floor-line" x1="' + x(fv) + '" y1="' + (cy - 9) + '" x2="' + x(fv) + '" y2="' + (cy + 9) + '"><title>floor: ' + fv.toFixed(1) + '</title></line>');
      }
      entries.forEach(function (e) {
        var v = e.types[t];
        if (!isNum(v)) return;
        parts.push('<circle class="' + dotClass(e) + '" cx="' + x(v) + '" cy="' + cy + '" r="7.5" tabindex="0" data-tip-id="' + e._id + '" data-tip-extra="' + esc(t) + ': ' + v.toFixed(1) + '">' +
          '<title>' + esc(e.name) + ', ' + esc(t) + ': ' + v.toFixed(1) + '</title></circle>');
      });
      if (top1 && top1.types && isNum(top1.types[t])) {
        parts.push('<text class="dlab" x="' + x(top1.types[t]) + '" y="' + (cy - 11) + '" text-anchor="middle">' + top1.types[t].toFixed(1) + '</text>');
      }
    });
    host.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Per field type scores, one dot per run' +
      (top1 ? '; labelled values are ' + esc(top1.name) : '') + '">' + parts.join('') + '</svg>';
  }

  /* ---------- latency vs index ---------- */

  function renderLatency() {
    var host = $('[data-latency-chart]'), g = state.groups;
    var pts = g.one.concat(g.two).filter(function (e) {
      return isNum(e.index) && e.latency_ms && isNum(e.latency_ms.median) && e.latency_ms.median > 0;
    });
    var W = Math.max(300, host.clientWidth || 480), H = Math.max(230, Math.round(W * 0.62)), left = 36, right = 18, top = 16, bottom = 42;
    var lats = pts.map(function (p) { return p.latency_ms.median; });
    var minLat = lats.some(function (v) { return v < 10; }) ? 1 : 10;
    var maxLat = Math.max(10000, Math.max.apply(null, lats.concat([0])) * 1.8);
    var lmin = Math.log10(minLat), lmax = Math.log10(maxLat);
    var x = function (v) { return left + (W - left - right) * (Math.log10(v) - lmin) / (lmax - lmin); };
    var y = function (v) { return top + (H - top - bottom) * (1 - clamp(v) / 100); };
    var parts = [HATCH_DEF];
    [0, 20, 40, 60, 80, 100].forEach(function (v) {
      parts.push('<line class="ax" x1="' + left + '" y1="' + y(v) + '" x2="' + (W - right) + '" y2="' + y(v) + '"/>');
      parts.push('<text class="tick" x="' + (left - 6) + '" y="' + (y(v) + 3.5) + '" text-anchor="end">' + v + '</text>');
    });
    for (var p = Math.ceil(lmin); p <= Math.floor(lmax); p++) {
      var v = Math.pow(10, p);
      var lab = v >= 1000 ? (v / 1000) + ' s' : v + ' ms';
      parts.push('<line class="ax" x1="' + x(v) + '" y1="' + top + '" x2="' + x(v) + '" y2="' + y(0) + '"/>');
      parts.push('<text class="tick" x="' + x(v) + '" y="' + (y(0) + 16) + '" text-anchor="middle">' + lab + '</text>');
    }
    parts.push('<line class="ax-base" x1="' + left + '" y1="' + y(0) + '" x2="' + (W - right) + '" y2="' + y(0) + '"/>');
    parts.push('<text class="tick lab" x="' + (W - right) + '" y="' + (H - 4) + '" text-anchor="end">median latency per request, log scale</text>');
    parts.push('<text class="tick lab" transform="translate(10 ' + y(50) + ') rotate(-90)" text-anchor="middle">Index</text>');
    // The corner you want: a faint highlighter wash, fast and strong.
    parts.unshift('<rect class="corner" x="' + left + '" y="' + top + '" width="' + Math.max(0, x(Math.min(300, maxLat)) - left) + '" height="' + Math.max(0, y(70) - top) + '" rx="6"/>');
    parts.push('<text class="corner-lab" x="' + (left + 8) + '" y="' + (top + 15) + '">fast and strong</text>');
    if (g.floor && isNum(g.floor.index)) {
      parts.push('<line class="floor-line" x1="' + left + '" y1="' + y(g.floor.index) + '" x2="' + (W - right) + '" y2="' + y(g.floor.index) + '"/>');
      parts.push('<text class="floor-lab" x="' + (W - right) + '" y="' + (y(g.floor.index) - 5) + '" text-anchor="end">floor ' + g.floor.index.toFixed(1) + '</text>');
    }
    if (!pts.length) {
      parts.push('<text class="dlab soft" x="' + ((left + W - right) / 2) + '" y="' + y(55) + '" text-anchor="middle">No timed runs yet</text>');
    }
    var maxLabels = W < 420 ? 4 : 8;
    var labelled = pts.length <= maxLabels ? pts.slice() : pts.slice().sort(sortDesc(function (e) { return e.index; })).slice(0, W < 420 ? 3 : 5);
    var useAvatars = pts.length <= 10;
    // Nudge labels apart vertically so a cluster of points stays readable.
    var labelY = {};
    labelled.sort(function (a, b) { return y(a.index) - y(b.index) || x(a.latency_ms.median) - x(b.latency_ms.median); });
    var prev = -Infinity;
    labelled.forEach(function (e) {
      var ly = Math.max(y(e.index), prev + 13);
      labelY[e._id] = ly;
      prev = ly;
    });
    pts.forEach(function (e, i) {
      var cx = x(e.latency_ms.median), cy = y(e.index);
      var src = useAvatars ? safeRel(e.avatar) : null;
      var tip = ' data-tip-id="' + e._id + '" data-tip-extra="median ' + fmtMs(e.latency_ms.median) + ' ms"';
      var title = '<title>' + esc(e.name) + ': Index ' + e.index.toFixed(1) + ', median ' + fmtMs(e.latency_ms.median) + ' ms</title>';
      if (src) {
        parts.push('<clipPath id="pt-clip-' + i + '"><circle cx="' + cx + '" cy="' + cy + '" r="10"/></clipPath>' +
          '<circle class="pt-ring" cx="' + cx + '" cy="' + cy + '" r="11.5"/>' +
          '<image href="' + esc(src) + '" x="' + (cx - 10) + '" y="' + (cy - 10) + '" width="20" height="20" clip-path="url(#pt-clip-' + i + ')" preserveAspectRatio="xMidYMid slice"/>' +
          '<circle class="pt-hit" cx="' + cx + '" cy="' + cy + '" r="11.5" tabindex="0"' + tip + '>' + title + '</circle>');
      } else {
        parts.push('<circle class="' + dotClass(e) + '" cx="' + cx + '" cy="' + cy + '" r="7" tabindex="0"' + tip + '>' + title + '</circle>');
      }
      if (labelled.indexOf(e) >= 0) {
        var name = String(e.name || '');
        if (name.length > 24) name = name.slice(0, 23) + '…';
        var anchor = cx > W - right - 150 ? 'end' : 'start';
        var ly = labelY[e._id], gap = src ? 15 : 11;
        var lx = anchor === 'start' ? cx + gap : cx - gap;
        if (ly - cy > 6) {
          parts.push('<line class="leader" x1="' + (anchor === 'start' ? cx + gap - 4 : cx - gap + 4) + '" y1="' + cy + '" x2="' + lx + '" y2="' + ly + '"/>');
        }
        parts.push('<text class="dlab' + (e.system === 'two' ? ' soft' : '') + '" x="' + lx + '" y="' + (ly + 4) + '" text-anchor="' + anchor + '">' + esc(name) + '</text>');
      }
    });
    host.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Median latency against Index, one point per run">' + parts.join('') + '</svg>';
    if (g.floor) {
      var note = $('[data-latency-note]');
      if (note && note.textContent.indexOf('null baseline') < 0) note.textContent += ' The null baseline has no latency; it is the dashed floor line.';
    }
  }

  /* ---------- tooltip ---------- */

  function entryById(id) {
    var all = state.groups ? state.groups.all : [];
    for (var i = 0; i < all.length; i++) if (all[i]._id === id) return all[i];
    return null;
  }
  function tipHtml(e, extra) {
    var areas = state.board.areas || [];
    var rows = [];
    rows.push('<div class="nr"><span>Index</span><b>' + fmtScore(e.index) + (isNum(e.index) ? '' : ' incomplete') + '</b></div>');
    areas.forEach(function (a) {
      rows.push('<div class="nr"><span><i style="--c:' + areaColour(a) + '"></i>' + esc(a) + '</span><b>' + fmtScore(e.areas ? e.areas[a] : null) + '</b></div>');
    });
    if (e.latency_ms && isNum(e.latency_ms.median)) {
      rows.push('<div class="nr"><span>Latency, median</span><b>' + fmtMs(e.latency_ms.median) + ' ms</b></div>');
    }
    var who = [e.org, e.system === 'two' ? 'System Two, reference' : e.system === 'baseline' ? 'floor' : (e.kind === 'open' ? 'open weights' : e.kind === 'api' ? 'API' : '')]
      .filter(Boolean).join(', ');
    return '<strong>' + esc(e.name) + '</strong>' + (who ? '<div class="ns">' + esc(who) + '</div>' : '') + rows.join('') +
      (extra ? '<div class="ns">' + esc(extra) + '</div>' : '');
  }
  function showTip(el) {
    var e = entryById(el.getAttribute('data-tip-id'));
    var tip = $('#tip');
    if (!e || !tip) return;
    tip.innerHTML = tipHtml(e, el.getAttribute('data-tip-extra'));
    tip.hidden = false;
    var r = el.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 8);
    var topPos = r.top - th - 10;
    if (topPos < 8) topPos = Math.min(r.bottom + 10, window.innerHeight - th - 8);
    tip.style.left = left + 'px';
    tip.style.top = topPos + 'px';
  }
  function hideTip() { var tip = $('#tip'); if (tip) tip.hidden = true; }
  function bindTips() {
    var over = function (ev) {
      var el = ev.target.closest ? ev.target.closest('[data-tip-id]') : null;
      if (el) showTip(el);
    };
    var out = function (ev) {
      var el = ev.target.closest ? ev.target.closest('[data-tip-id]') : null;
      if (el && !(ev.relatedTarget && el.contains(ev.relatedTarget))) hideTip();
    };
    document.addEventListener('mouseover', over);
    document.addEventListener('mouseout', out);
    document.addEventListener('focusin', over);
    document.addEventListener('focusout', out);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') hideTip(); });
    window.addEventListener('scroll', hideTip, { passive: true });
  }

  /* ---------- full table ---------- */

  function sortValue(e, key) {
    if (key === 'index') return e.index;
    if (key === 'latency') return e.latency_ms ? e.latency_ms.median : null;
    if (key.indexOf('area:') === 0) return e.areas ? e.areas[key.slice(5)] : null;
    return null;
  }
  function sortRows(rows) {
    var key = state.sort.key, m = state.sort.dir === 'desc' ? -1 : 1;
    return rows.slice().sort(function (a, b) {
      var va = sortValue(a, key), vb = sortValue(b, key);
      var na = !isNum(va), nb = !isNum(vb);
      if (na && nb) return a._i - b._i;
      if (na) return 1;
      if (nb) return -1;
      if (va !== vb) return (va - vb) * m;
      return a._i - b._i;
    });
  }

  function scoreCell(v, opts) {
    opts = opts || {};
    if (!isNum(v)) {
      return '<span class="na">—</span>' + (opts.incomplete ? '<span class="small">incomplete</span>' : '');
    }
    return '<span class="score"><span class="n">' + v.toFixed(1) + '</span>' +
      '<span class="bar" aria-hidden="true"><i style="width:' + clamp(v) + '%' + (opts.c ? ';--c:' + opts.c : '') + '"></i></span></span>';
  }
  function miniScore(v, c) {
    if (!isNum(v)) return '<span class="v na">—</span><span class="bar" aria-hidden="true"></span>';
    return '<span class="v">' + v.toFixed(1) + '</span><span class="bar" aria-hidden="true"><i style="width:' + clamp(v) + '%' + (c ? ';--c:' + c : '') + '"></i></span>';
  }

  function detailHtml(e) {
    var tests = state.board.tests || [];
    var testRows = tests.map(function (t) {
      var v = e.tests ? e.tests[t.name] : null, c = areaColour(t.area);
      return '<li><span class="k"><i style="--c:' + c + '" aria-hidden="true"></i>' + esc(t.title || t.name) + '</span>' + miniScore(v, c) + '</li>';
    }).join('');
    var types = Object.keys(e.types || {}).sort(function (a, b) {
      var ia = TYPE_ORDER.indexOf(a), ib = TYPE_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    var typeRows = types.map(function (t) {
      return '<li><span class="k"><code>' + esc(t) + '</code></span>' + miniScore(e.types[t]) + '</li>';
    }).join('') || '<li class="muted">Not reported</li>';
    var n = e.null || {}, l = e.latency_ms || {}, links = e.links || {};
    var linkItems = [['model', 'Model'], ['results', 'Results'], ['submission', 'Submission']].map(function (p) {
      var u = safeUrl(links[p[0]]);
      return u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + p[1] + '</a>' : '';
    }).filter(Boolean).join('');
    var latency = isNum(l.median) || isNum(l.mean) || isNum(l.p80)
      ? fmtMs(l.median) + ' / ' + fmtMs(l.mean) + ' / ' + fmtMs(l.p80) + ' ms'
      : '—';
    var nulls = isNum(n.precision) || isNum(n.recall) ? fmtPct(n.precision) + ' / ' + fmtPct(n.recall) : '—';
    var r = e.rows || {};
    var rowsText = '—';
    if (isNum(r.total)) {
      var bits = [fmtInt(r.ok || 0) + ' ok', fmtInt(r.unsupported || 0) + ' unsupported'];
      if (r.error) bits.push(fmtInt(r.error) + ' error');
      if (r.missing) bits.push(fmtInt(r.missing) + ' missing');
      rowsText = fmtInt(r.total) + ' requests: ' + bits.join(', ');
    }
    // The run facts print as a receipt slip.
    return '<div class="dcol"><h4>Tests</h4><ul class="scores">' + testRows + '</ul></div>' +
      '<div class="dcol"><h4>Field types</h4><ul class="scores">' + typeRows + '</ul></div>' +
      '<div class="dcol"><h4>Run</h4><div class="receipt run-slip"><dl>' +
      '<div><dt>Null precision / recall</dt><dd>' + nulls + '</dd></div>' +
      '<div><dt>Latency med / mean / p80</dt><dd>' + latency + '</dd></div>' +
      '<div><dt>Date</dt><dd>' + esc(fmtDate(e.date)) + '</dd></div>' +
      '<div class="wide"><dt>Rows</dt><dd>' + esc(rowsText) + '</dd></div>' +
      '<div class="wide"><dt>Hardware</dt><dd>' + esc(e.hardware || '—') + '</dd></div>' +
      '<div class="wide"><dt>Links</dt><dd class="links">' + (linkItems || '—') + '</dd></div>' +
      (e.notes ? '<div class="wide"><dt>Notes</dt><dd>' + esc(e.notes) + '</dd></div>' : '') +
      '</dl></div></div>';
  }

  function rowHtml(e, areas) {
    var two = e.system === 'two', base = e.system === 'baseline';
    var open = !!state.open[e._id];
    var rankCell = two ? '<span class="na" title="Reference row, not ranked">ref</span>'
      : base ? '<span class="na" title="The null floor, not ranked">floor</span>'
      : (e._rank ? String(e._rank) : '<span class="na" title="Incomplete run, not ranked">—</span>');
    var cols = 4 + areas.length;
    return '<tr class="row' + (two ? ' two' : '') + (base ? ' base' : '') + (open ? ' open' : '') + '" data-id="' + e._id + '">' +
      '<td class="c-rank">' + rankCell + '</td>' +
      '<td class="c-model"><div class="model-cell">' + avatarHtml(e) + '<div>' +
        '<button type="button" class="expand" aria-expanded="' + open + '" aria-controls="' + e._id + '-detail">' +
          '<svg class="chev" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          '<span class="name">' + esc(e.name || 'Unnamed') + '</span>' +
        '</button>' +
        '<span class="org">' + (e.org ? '<span>' + esc(e.org) + '</span>' : '') + kindPill(e) + '</span>' +
      '</div></div></td>' +
      '<td class="c-score c-index">' + scoreCell(e.index, { incomplete: !two && !base && !isNum(e.index) }) + '</td>' +
      areas.map(function (a) { return '<td class="c-score">' + scoreCell(e.areas ? e.areas[a] : null, { c: areaColour(a) }) + '</td>'; }).join('') +
      '<td class="c-lat">' + (base ? '<span class="na">—</span>' : fmtMs(e.latency_ms ? e.latency_ms.median : null)) + '</td>' +
      '</tr>' +
      '<tr class="detail" id="' + e._id + '-detail"' + (open ? '' : ' hidden') + '><td colspan="' + cols + '"><div class="detail-inner">' + detailHtml(e) + '</div></td></tr>';
  }

  function sortIcon() {
    return '<svg class="dir" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  function groupRow(cols, text) {
    return '<tr class="group"><th scope="rowgroup" colspan="' + cols + '"><div class="group-inner">' + text + '</div></th></tr>';
  }

  function renderTable() {
    var board = state.board, host = $('#table'), g = state.groups;
    var areas = board.areas || [];
    if (!g.all.length) {
      host.innerHTML = '<div class="empty"><p>No runs yet.</p></div>';
      return;
    }
    var headCells = [
      '<th scope="col" class="c-rank"><span aria-hidden="true">#</span><span class="sr-only">Rank</span></th>',
      '<th scope="col" class="c-model">Model</th>'
    ];
    var sortable = [{ key: 'index', label: 'Index', cls: 'c-score c-index' }]
      .concat(areas.map(function (a) { return { key: 'area:' + a, label: a, cls: 'c-score', c: areaColour(a) }; }))
      .concat([{ key: 'latency', label: 'Latency', unit: 'median ms', cls: 'c-lat' }]);
    sortable.forEach(function (c) {
      var sorted = state.sort.key === c.key;
      var aria = sorted ? (state.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
      headCells.push('<th scope="col" class="' + c.cls + '" aria-sort="' + aria + '">' +
        '<button type="button" class="sort" data-key="' + esc(c.key) + '">' +
        (c.c ? '<i class="adot" style="--c:' + c.c + '" aria-hidden="true"></i>' : '') + esc(c.label) + sortIcon() + '</button>' +
        (c.unit ? '<span class="unit">' + c.unit + '</span>' : '') + '</th>');
    });
    var cols = 4 + areas.length;
    var html = '<div class="scroller"><table class="board">' +
      '<caption class="sr-only">System One extraction models ranked by Index, then the null floor and System Two reference rows</caption>' +
      '<thead><tr>' + headCells.join('') + '</tr></thead>';
    if (g.one.length) {
      html += '<tbody>' + sortRows(g.one).map(function (e) { return rowHtml(e, areas); }).join('') + '</tbody>';
    }
    if (g.base.length) {
      html += '<tbody>' + groupRow(cols, 'Floor: answers null for every field. Each test scores its share of null gold fields') +
        g.base.map(function (e) { return rowHtml(e, areas); }).join('') + '</tbody>';
    }
    if (g.two.length) {
      html += '<tbody>' + groupRow(cols, 'System Two reference: generating models prompted for JSON, shown for comparison, not ranked') +
        sortRows(g.two).map(function (e) { return rowHtml(e, areas); }).join('') + '</tbody>';
    }
    html += '</table></div>';
    host.innerHTML = html;
    syncScrollerWidth();
  }

  function syncScrollerWidth() {
    var sc = $('#table .scroller');
    if (sc) sc.style.setProperty('--vw', sc.clientWidth + 'px');
  }

  function toggleRow(id, force) {
    var row = $('#table tr.row[data-id="' + id + '"]');
    var det = document.getElementById(id + '-detail');
    if (!row || !det) return;
    var open = typeof force === 'boolean' ? force : !state.open[id];
    if (open) state.open[id] = true; else delete state.open[id];
    row.classList.toggle('open', open);
    row.querySelector('.expand').setAttribute('aria-expanded', String(open));
    det.hidden = !open;
    if (open) {
      history.replaceState(null, '', '#' + id);
    } else if (location.hash === '#' + id) {
      history.replaceState(null, '', location.pathname + location.search);
    }
  }

  function jumpToRow(id) {
    toggleRow(id, true);
    var row = $('#table tr.row[data-id="' + id + '"]');
    if (!row) return;
    row.scrollIntoView({ block: 'center' });
    var btn = row.querySelector('.expand');
    if (btn) btn.focus({ preventScroll: true });
  }

  function bindBoardEvents() {
    $('#table').addEventListener('click', function (ev) {
      var sortBtn = ev.target.closest('.sort');
      if (sortBtn) {
        var key = sortBtn.getAttribute('data-key');
        if (state.sort.key === key) {
          state.sort.dir = state.sort.dir === 'desc' ? 'asc' : 'desc';
        } else {
          state.sort = { key: key, dir: key === 'latency' ? 'asc' : 'desc' };
        }
        renderTable();
        var again = $('#table .sort[data-key="' + key + '"]');
        if (again) again.focus();
        return;
      }
      if (ev.target.closest('a')) return;
      var row = ev.target.closest('tr.row');
      if (row) {
        var sel = window.getSelection && window.getSelection();
        if (sel && String(sel).length && !ev.target.closest('.expand')) return;
        toggleRow(row.getAttribute('data-id'));
      }
    });
    $('#ranking').addEventListener('click', function (ev) {
      var bar = ev.target.closest('.stroke');
      if (bar) { hideTip(); jumpToRow(bar.getAttribute('data-id')); }
    });
    $('[data-switch]').addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-metric]');
      if (!btn) return;
      state.metric = btn.getAttribute('data-metric');
      renderSwitch();
      renderLegend();
      renderRanking();
      var again = $('[data-switch] button[data-metric="' + state.metric + '"]');
      if (again) again.focus();
    });
    var newsBtn = $('#news-toggle'), news = $('#news');
    if (newsBtn && news) {
      newsBtn.addEventListener('click', function () {
        var open = news.hidden;
        news.hidden = !open;
        newsBtn.setAttribute('aria-expanded', String(open));
      });
    }
  }

  /* ---------- index tabs: mark the section in view ---------- */

  function bindTabs() {
    var links = $all('.tabs a[href^="#"]');
    if (!links.length) return;
    var targets = links.map(function (a) {
      return { a: a, el: document.getElementById(a.getAttribute('href').slice(1)) };
    }).filter(function (t) { return t.el; });
    var ticking = false;
    function update() {
      ticking = false;
      var current = null, line = 140;
      targets.forEach(function (t) {
        if (t.el.getBoundingClientRect().top <= line) current = t;
      });
      targets.forEach(function (t) {
        if (t === current) t.a.setAttribute('aria-current', 'true'); else t.a.removeAttribute('aria-current');
      });
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  function openFromHash() {
    var h = location.hash.replace(/^#/, '');
    if (!h || h.indexOf('entry-') !== 0) return;
    var row = $('#table tr.row[data-id="' + h + '"]');
    if (!row) return;
    toggleRow(h, true);
    row.scrollIntoView({ block: 'start' });
  }

  /* ---------- tests ---------- */

  function testCard(t) {
    var src = safeUrl(t.source_url);
    var types = (t.types || []).map(function (x) { return '<code>' + esc(x) + '</code>'; }).join(' ');
    return '<article class="card test" id="test-' + esc(t.name) + '" style="--c:' + areaColour(t.area) + '">' +
      '<header><h4>' + esc(t.title || t.name) + '</h4><code class="tid">' + esc(t.name) + '</code></header>' +
      '<p>' + esc(t.description || '') + '</p>' +
      '<dl class="facts-grid">' +
      '<div><dt>Requests</dt><dd>' + fmtInt(t.requests) + '</dd></div>' +
      '<div><dt>Fields</dt><dd>' + fmtInt(t.fields) + '</dd></div>' +
      '<div><dt>Null share</dt><dd>' + fmtShare(t.null_share) + '</dd></div>' +
      '<div><dt>Metric</dt><dd>' + esc(t.metric || '—') + '</dd></div>' +
      '<div class="wide"><dt>Field types</dt><dd>' + (types || '—') + '</dd></div>' +
      '<div><dt>Licence</dt><dd>' + esc(t.license || '—') + '</dd></div>' +
      '<div><dt>Source</dt><dd>' + (src ? '<a href="' + esc(src) + '" target="_blank" rel="noopener">' + esc(hostOf(src)) + '</a>' : '—') + '</dd></div>' +
      '</dl></article>';
  }

  function renderTests() {
    var board = state.board, host = $('#tests-body');
    var tests = board.tests || [];
    var areas = (board.areas || []).slice();
    tests.forEach(function (t) { if (t.area && areas.indexOf(t.area) < 0) areas.push(t.area); });
    var html = areas.map(function (a) {
      var ts = tests.filter(function (t) { return t.area === a; });
      if (!ts.length) return '';
      return '<div class="area" style="--c:' + areaColour(a) + '"><h3>' + stickerHtml(a, 56) + esc(a) + ' <span class="count">' + plural(ts.length, 'test') + '</span></h3>' +
        '<div class="tests-grid">' + ts.map(testCard).join('') + '</div></div>';
    }).join('');
    host.innerHTML = html || '<div class="card empty"><p>No tests listed in the board file.</p></div>';
  }

  /* ---------- page text ---------- */

  function renderMeta() {
    var board = state.board, g = state.groups, tests = board.tests || [];
    if (board.edition) setText('[data-edition]', board.edition);
    setText('[data-test-count]', String(tests.length || 7));
    var gen = fmtDate(board.generated_utc);
    setText('[data-generated]', gen);
    var requests = tests.reduce(function (s, t) { return s + (isNum(t.requests) ? t.requests : 0); }, 0);
    var fieldsKnown = tests.length && tests.every(function (t) { return isNum(t.fields); });
    var fields = tests.reduce(function (s, t) { return s + (isNum(t.fields) ? t.fields : 0); }, 0);
    setText('[data-request-count]', fmtInt(requests));
    var areas = (board.areas || []).length;
    setText('[data-tests-meta]', plural(tests.length, 'test') + ' in ' + plural(areas, 'area') + ', ' + fmtInt(requests) + ' requests' +
      (fieldsKnown ? ', ' + fmtInt(fields) + ' fields' : '') + '. Public sources, pinned revisions, fixed seed.');
    var ranked = g.ranked.length;
    var meta = ['edition ' + (board.edition || '?'), plural(tests.length, 'test'), fmtInt(requests) + ' requests',
      ranked + (ranked === 1 ? ' ranked entry' : ' ranked entries')];
    if (g.two.length) meta.push(plural(g.two.length, 'reference row'));
    meta.push('updated ' + gen);
    $all('[data-meta]').forEach(function (el) {
      el.innerHTML = meta.map(function (t) { return '<span>' + esc(t) + '</span>'; }).join('');
    });
    var bits = [];
    if (ranked) bits.push(ranked + (ranked === 1 ? ' ranked entry' : ' ranked entries'));
    if (g.one.length - ranked) bits.push(plural(g.one.length - ranked, 'incomplete run'));
    if (g.base.length) bits.push('the null floor');
    if (g.two.length) bits.push(plural(g.two.length, 'reference row'));
    setText('[data-board-meta]', (bits.join(', ') || 'no rows') + ' · generated ' + gen);
  }

  function showError(msg) {
    var host = $('#ranking');
    host.setAttribute('aria-busy', 'false');
    host.innerHTML = '<div class="error"><h3>Could not load the board</h3><p>' + esc(msg) + ' The file <code>data/board.json</code> is generated by <code>python -m extract_index board</code>.</p></div>';
  }

  function renderAll() {
    renderMeta();
    renderLegend();
    renderSwitch();
    renderRanking();
    renderAreas();
    renderTypes();
    renderLatency();
    renderTable();
    renderTests();
  }

  function init() {
    renderJsonExamples();
    bindBoardEvents();
    bindTips();
    bindTabs();

    fetch(BOARD_URL, { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + BOARD_URL + '.'); return r.json(); })
      .then(function (board) {
        if (!board || typeof board !== 'object') throw new Error('The board file is not a JSON object.');
        state.board = board;
        state.groups = prepareEntries(board);
        renderAll();
        openFromHash();
      })
      .catch(function (err) { showError(err && err.message ? err.message : String(err)); });

    var t, lastW = window.innerWidth;
    window.addEventListener('resize', function () {
      clearTimeout(t);
      t = setTimeout(function () {
        if (!state.groups) return;
        if (window.innerWidth !== lastW) { lastW = window.innerWidth; renderRanking(); renderTypes(); renderLatency(); }
        syncScrollerWidth();
      }, 120);
    });
    window.addEventListener('hashchange', openFromHash);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
