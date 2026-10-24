/* SystemOne Extract Index: leaderboard page.
   Everything score-like on this page comes from data/board.json. */
(function () {
  'use strict';

  var BOARD_URL = 'data/board.json';
  var TYPE_ORDER = ['text', 'number', 'date', 'time', 'datetime', 'duration', 'list'];

  var state = {
    board: null,
    sort: { key: 'index', dir: 'desc' },
    open: {}
  };

  // Dev convenience: ?theme=dark|light forces a theme without touching OS settings.
  var themeParam = new URLSearchParams(location.search).get('theme');
  if (themeParam === 'dark' || themeParam === 'light') {
    document.documentElement.setAttribute('data-theme', themeParam);
  }

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
  // Ratios may arrive as 0-1 or 0-100; show both as a percentage.
  function fmtShare(v) { return isNum(v) ? Math.round(v * 100) + '%' : '—'; }  // 0-1 shares
  function fmtPct(v) { return isNum(v) ? Math.round(v) + '%' : '—'; }  // 0-100 scores
  function fmtDate(s) {
    if (!s) return '—';
    var m = String(s).match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : String(s);
  }
  function safeUrl(u) { return (typeof u === 'string' && /^https?:\/\//i.test(u)) ? u : null; }
  function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return u; } }
  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''); }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  function setText(sel, text) { $all(sel).forEach(function (el) { el.textContent = text; }); }

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
      } else if (tok === 'true' || tok === 'false') {
        out += '<span class="j-num">' + tok + '</span>';
      } else {
        out += '<span class="j-num">' + esc(tok) + '</span>';
      }
      last = m.index + tok.length;
    }
    out += esc(src.slice(last));
    return out;
  }

  function renderJsonExamples() {
    $all('code[data-json]').forEach(function (el) {
      el.innerHTML = highlightJson(el.textContent);
    });
  }

  /* ---------- diagram ---------- */

  var ICONS = {
    doc: '<path d="M4 2h6l3 3v9H4z"/><path d="M10 2v3h3"/><path d="M6.5 8.5h4M6.5 11h4"/>',
    chip: '<rect x="4.5" y="4.5" width="7" height="7" rx="1.5"/><path d="M6.5 1.5v3M9.5 1.5v3M6.5 11.5v3M9.5 11.5v3M1.5 6.5h3M1.5 9.5h3M11.5 6.5h3M11.5 9.5h3"/>',
    braces: '<path d="M6 2.5c-1.8 0-2 1-2 2.5v1.5c0 1-.6 1.5-1.5 1.5.9 0 1.5.5 1.5 1.5V11c0 1.5.2 2.5 2 2.5"/><path d="M10 2.5c1.8 0 2 1 2 2.5v1.5c0 1 .6 1.5 1.5 1.5-.9 0-1.5.5-1.5 1.5V11c0 1.5-.2 2.5-2 2.5"/>',
    check: '<circle cx="8" cy="8" r="6"/><path d="M5.3 8.2l1.9 1.9 3.6-4.2"/>',
    bars: '<path d="M3 13.5V8M8 13.5V3.5M13 13.5V10"/><path d="M1.5 13.5h13"/>',
    sigma: '<path d="M12 3.5H4.5l4 4.5-4 4.5H12"/>'
  };

  function diagramNodes() {
    var n = (state.board && state.board.tests && state.board.tests.length) || 7;
    return [
      { title: 'Request', icon: 'doc',
        text: 'state (the document) and fields: a map of name to type, with optional instructions, unit, decimals.' },
      { title: 'Model', icon: 'chip', accent: true,
        text: 'One forward pass over state and fields. No decoding, no generated tokens.' },
      { title: 'Answers', icon: 'braces',
        text: 'One typed value or null per field. Optional p_null, confidence and span.' },
      { title: 'Scorer', icon: 'check',
        text: 'Each field against gold, with the rule for its type. A score in 0 to 1.' },
      { title: 'Test score', icon: 'bars',
        text: 'Mean field score × 100. One score per test.' },
      { title: 'Index', icon: 'sigma', last: true,
        text: 'Mean of the ' + n + ' test scores, 0 to 100.' }
    ];
  }
  var GROUPS = [
    { from: 0, to: 2, label: 'Engine under test' },
    { from: 3, to: 5, label: 'Kit, deterministic: python -m extract_index score' }
  ];

  var measureCtx = null;
  function textWidth(text, px, weight) {
    if (!measureCtx) {
      var c = document.createElement('canvas');
      measureCtx = c.getContext('2d');
    }
    measureCtx.font = (weight || 400) + ' ' + px + 'px "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif';
    return measureCtx.measureText(text).width;
  }
  function wrap(text, maxW, px) {
    var words = text.split(' '), lines = [], cur = '';
    words.forEach(function (w) {
      var t = cur ? cur + ' ' + w : w;
      if (cur && textWidth(t, px) > maxW) { lines.push(cur); cur = w; } else { cur = t; }
    });
    if (cur) lines.push(cur);
    return lines;
  }
  function svgText(x, y, cls, lines, lh) {
    return lines.map(function (l, i) {
      return '<text class="' + cls + '" x="' + x + '" y="' + (y + i * lh) + '">' + esc(l) + '</text>';
    }).join('');
  }
  function svgIcon(x, y, name, accent) {
    return '<g class="icon' + (accent ? ' accent' : '') + '" transform="translate(' + x + ' ' + y + ')">' + ICONS[name] + '</g>';
  }
  function boxClass(nd) { return 'box' + (nd.accent ? ' accent' : '') + (nd.last ? ' last' : ''); }

  function layoutHorizontal(nodes, W) {
    var pad = 10, gap = 22, ggap = 40, capH = 24, bodyPx = 11.5, lh = 15;
    var boxW = Math.floor((W - 4 * pad - ggap - 4 * gap) / 6);
    var innerW = boxW - 20;
    var wrapped = nodes.map(function (nd) { return wrap(nd.text, innerW, bodyPx); });
    var maxLines = Math.max.apply(null, wrapped.map(function (l) { return l.length; }));
    var boxH = 44 + maxLines * lh + 6;
    var top = capH + pad, H = top + boxH + pad;
    var xs = [], x = pad;
    nodes.forEach(function (nd, i) {
      xs.push(x);
      x += boxW + (i === 2 ? pad + ggap + pad : gap);
    });
    var out = [];
    GROUPS.forEach(function (g) {
      var gx = xs[g.from] - pad, gw = xs[g.to] + boxW + pad - gx;
      out.push('<rect class="group" x="' + gx + '" y="0" width="' + gw + '" height="' + H + '" rx="10"/>');
      out.push('<text class="t-cap" x="' + (gx + pad + 2) + '" y="16">' + esc(g.label) + '</text>');
    });
    nodes.forEach(function (nd, i) {
      var bx = xs[i];
      out.push('<rect class="' + boxClass(nd) + '" x="' + bx + '" y="' + top + '" width="' + boxW + '" height="' + boxH + '" rx="8"/>');
      out.push(svgIcon(bx + 10, top + 11, nd.icon, nd.accent));
      out.push('<text class="t-title" x="' + (bx + 32) + '" y="' + (top + 24) + '">' + esc(nd.title) + '</text>');
      out.push(svgText(bx + 10, top + 44 + 9, 't-body', wrapped[i], lh));
      if (i < nodes.length - 1) {
        var y = top + boxH / 2, x1 = bx + boxW + 1, x2 = xs[i + 1] - 1;
        out.push('<path class="link" d="M' + x1 + ' ' + y + 'H' + x2 + '" marker-end="url(#diag-arrow)"/>');
      }
    });
    return { body: out.join(''), W: W, H: H, cls: 'horiz' };
  }

  function layoutVertical(nodes, W) {
    var pad = 10, gap = 30, ggap = 40, capH = 24, bodyPx = 12.5, lh = 17;
    var boxW = W - 2 * pad, innerW = boxW - 20;
    var out = [], y = 0, groupStart = 0;
    var rects = [];
    nodes.forEach(function (nd, i) {
      var g = GROUPS[i === 0 ? 0 : (i === 3 ? 1 : -1)];
      if (g) { groupStart = y; y += capH + pad; }
      var lines = wrap(nd.text, innerW, bodyPx);
      var h = 44 + lines.length * lh + 4;
      rects.push({ x: pad, y: y, w: boxW, h: h, lines: lines });
      y += h;
      if (i === 2 || i === 5) {
        var gEnd = y + pad;
        var gi = i === 2 ? 0 : 1;
        out.unshift('<rect class="group" x="0" y="' + groupStart + '" width="' + W + '" height="' + (gEnd - groupStart) + '" rx="10"/>' +
          '<text class="t-cap" x="' + (pad + 2) + '" y="' + (groupStart + 16) + '">' + esc(GROUPS[gi].label) + '</text>');
        y = gEnd + (i === 2 ? ggap : 0);
      } else {
        y += gap;
      }
    });
    var H = y;
    nodes.forEach(function (nd, i) {
      var r = rects[i];
      out.push('<rect class="' + boxClass(nd) + '" x="' + r.x + '" y="' + r.y + '" width="' + r.w + '" height="' + r.h + '" rx="8"/>');
      out.push(svgIcon(r.x + 10, r.y + 11, nd.icon, nd.accent));
      out.push('<text class="t-title" x="' + (r.x + 32) + '" y="' + (r.y + 24) + '">' + esc(nd.title) + '</text>');
      out.push(svgText(r.x + 10, r.y + 44 + 9, 't-body', r.lines, lh));
      if (i < nodes.length - 1) {
        var cx = r.x + 24, y1 = r.y + r.h + 1, y2 = rects[i + 1].y - 1;
        out.push('<path class="link" d="M' + cx + ' ' + y1 + 'V' + y2 + '" marker-end="url(#diag-arrow)"/>');
      }
    });
    return { body: out.join(''), W: W, H: H, cls: 'vert' };
  }

  var lastDiagramWidth = 0;
  function renderDiagram(force) {
    var host = $('#diagram');
    if (!host) return;
    var W = host.clientWidth;
    if (!W || (!force && W === lastDiagramWidth)) return;
    lastDiagramWidth = W;
    var nodes = diagramNodes();
    var lay = W >= 860 ? layoutHorizontal(nodes, W) : layoutVertical(nodes, Math.min(W, 560));
    host.innerHTML =
      '<svg class="diag ' + lay.cls + '" width="' + lay.W + '" height="' + lay.H + '" viewBox="0 0 ' + lay.W + ' ' + lay.H + '" role="img" aria-labelledby="diag-title diag-desc">' +
      '<title id="diag-title">How a run is scored</title>' +
      '<desc id="diag-desc">A request with state and typed field specs goes to the model, which makes one pass and returns a typed value or null per field. The scorer compares each field with gold, each test gets the mean field score times 100, and the Index is the mean of the test scores.</desc>' +
      '<defs><marker id="diag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="arrow" d="M1 1.5L8.5 5 1 8.5z"/></marker></defs>' +
      lay.body + '</svg>';
  }

  /* ---------- leaderboard ---------- */

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
    var one = entries.filter(function (e) { return e.system !== 'two'; });
    var two = entries.filter(function (e) { return e.system === 'two'; });
    var ranked = one.filter(function (e) { return isNum(e.index); }).sort(function (a, b) { return b.index - a.index; });
    var rank = 0;
    ranked.forEach(function (e, i) {
      if (i === 0 || e.index < ranked[i - 1].index) rank = i + 1;
      e._rank = rank;
    });
    return { one: one, two: two, all: entries };
  }

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
      '<span class="bar" aria-hidden="true"><i style="width:' + clamp(v) + '%"></i></span></span>';
  }
  function miniScore(v) {
    if (!isNum(v)) return '<span class="v na">—</span><span class="bar" aria-hidden="true"></span>';
    return '<span class="v">' + v.toFixed(1) + '</span><span class="bar" aria-hidden="true"><i style="width:' + clamp(v) + '%"></i></span>';
  }
  function kindTag(kind) {
    if (kind === 'open') return '<span class="tag tag-open">Open weights</span>';
    if (kind === 'api') return '<span class="tag">API</span>';
    return kind ? '<span class="tag">' + esc(kind) + '</span>' : '';
  }

  function detailHtml(e) {
    var tests = state.board.tests || [];
    var testRows = tests.map(function (t) {
      var v = e.tests ? e.tests[t.name] : null;
      return '<li><span class="k">' + esc(t.title || t.name) + '</span>' + miniScore(v) + '</li>';
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
      return u ? '<a href="' + esc(u) + '" rel="noopener">' + p[1] + '</a>' : '';
    }).filter(Boolean).join('');
    var latency = isNum(l.median) || isNum(l.mean) || isNum(l.p80)
      ? fmtMs(l.median) + ' / ' + fmtMs(l.mean) + ' / ' + fmtMs(l.p80) + ' ms'
      : '—';
    var nulls = isNum(n.precision) || isNum(n.recall)
      ? fmtPct(n.precision) + ' / ' + fmtPct(n.recall)
      : '—';
    var r = e.rows || {};
    var rowsText = isNum(r.total)
      ? r.total.toLocaleString('en-US') + ' requests: ' + (r.ok || 0).toLocaleString('en-US') + ' ok, ' +
        (r.unsupported || 0).toLocaleString('en-US') + ' unsupported'
      : '—';
    return '<div class="dcol"><h4>Tests</h4><ul class="scores">' + testRows + '</ul></div>' +
      '<div class="dcol"><h4>Field types</h4><ul class="scores">' + typeRows + '</ul></div>' +
      '<div class="dcol dfacts"><h4>Run</h4><dl>' +
      '<dt>Null precision / recall</dt><dd>' + nulls + '</dd>' +
      '<dt>Latency median / mean / p80</dt><dd>' + latency + '</dd>' +
      '<dt>Rows</dt><dd>' + esc(rowsText) + '</dd>' +
      '<dt>Hardware</dt><dd>' + esc(e.hardware || '—') + '</dd>' +
      '<dt>Date</dt><dd>' + esc(fmtDate(e.date)) + '</dd>' +
      '<dt>Links</dt><dd class="links">' + (linkItems || '—') + '</dd>' +
      (e.notes ? '<dt>Notes</dt><dd>' + esc(e.notes) + '</dd>' : '') +
      '</dl></div>';
  }

  function rowHtml(e, areas) {
    var ref = e.system === 'two';
    var open = !!state.open[e._id];
    var rankCell = ref
      ? '<span class="na" title="Reference row, not ranked">—</span>'
      : (e._rank ? String(e._rank) : '<span class="na" title="Incomplete run, not ranked">—</span>');
    var cols = 4 + areas.length;
    return '<tr class="row' + (ref ? ' ref' : '') + (open ? ' open' : '') + '" data-id="' + e._id + '">' +
      '<td class="c-rank">' + rankCell + '</td>' +
      '<td class="c-model">' +
        '<button type="button" class="expand" aria-expanded="' + open + '" aria-controls="' + e._id + '-detail">' +
          '<svg class="chev" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          '<span class="name">' + esc(e.name || 'Unnamed') + '</span>' +
        '</button>' +
        '<span class="org">' + (e.org ? '<span>' + esc(e.org) + '</span>' : '') + kindTag(e.kind) +
          (ref ? '<span class="tag tag-ref">System Two, reference</span>' : '') + '</span>' +
      '</td>' +
      '<td class="c-score c-index">' + scoreCell(e.index, { incomplete: !ref && !isNum(e.index) }) + '</td>' +
      areas.map(function (a) { return '<td class="c-score">' + scoreCell(e.areas ? e.areas[a] : null) + '</td>'; }).join('') +
      '<td class="c-lat">' + fmtMs(e.latency_ms ? e.latency_ms.median : null) + '</td>' +
      '</tr>' +
      '<tr class="detail" id="' + e._id + '-detail"' + (open ? '' : ' hidden') + '><td colspan="' + cols + '"><div class="detail-inner">' + detailHtml(e) + '</div></td></tr>';
  }

  function sortIcon() {
    return '<svg class="dir" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  function renderBoard() {
    var board = state.board, host = $('#board');
    var areas = board.areas || [];
    var groups = prepareEntries(board);
    host.setAttribute('aria-busy', 'false');

    if (!groups.all.length) {
      host.innerHTML = '<div class="empty"><h3>No runs yet</h3>' +
        '<p>Scored runs appear here once they are merged. The first ones are scheduled after the suite is frozen. ' +
        'To add yours, see <a href="#submit">Submit a run</a>.</p></div>';
      return;
    }

    var headCells = [
      '<th scope="col" class="c-rank"><span aria-hidden="true">#</span><span class="sr-only">Rank</span></th>',
      '<th scope="col" class="c-model">Model</th>'
    ];
    var sortable = [{ key: 'index', label: 'Index', cls: 'c-score c-index' }]
      .concat(areas.map(function (a) { return { key: 'area:' + a, label: a, cls: 'c-score' }; }))
      .concat([{ key: 'latency', label: 'Latency', unit: 'median ms', cls: 'c-lat' }]);
    sortable.forEach(function (c) {
      var sorted = state.sort.key === c.key;
      var aria = sorted ? (state.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
      headCells.push('<th scope="col" class="' + c.cls + '" aria-sort="' + aria + '">' +
        '<button type="button" class="sort" data-key="' + c.key + '">' + esc(c.label) + sortIcon() + '</button>' +
        (c.unit ? '<span class="unit">' + c.unit + '</span>' : '') + '</th>');
    });

    var cols = 4 + areas.length;
    var html = '<div class="scroller"><table class="board">' +
      '<caption class="sr-only">System One extraction models ranked by Index, with System Two reference rows below</caption>' +
      '<thead><tr>' + headCells.join('') + '</tr></thead>';
    if (groups.one.length) {
      html += '<tbody>' + sortRows(groups.one).map(function (e) { return rowHtml(e, areas); }).join('') + '</tbody>';
    }
    if (groups.two.length) {
      html += '<tbody><tr class="group"><th scope="rowgroup" colspan="' + cols + '"><div class="group-inner">System Two reference: generating models prompted for JSON, shown for comparison, not ranked</div></th></tr>' +
        sortRows(groups.two).map(function (e) { return rowHtml(e, areas); }).join('') + '</tbody>';
    }
    html += '</table></div>';
    host.innerHTML = html;
    syncScrollerWidth();
  }

  function syncScrollerWidth() {
    var sc = $('#board .scroller');
    if (sc) sc.style.setProperty('--vw', sc.clientWidth + 'px');
  }

  function toggleRow(id, force) {
    var row = $('#board tr.row[data-id="' + id + '"]');
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

  function bindBoardEvents() {
    var host = $('#board');
    host.addEventListener('click', function (ev) {
      var sortBtn = ev.target.closest('.sort');
      if (sortBtn) {
        var key = sortBtn.getAttribute('data-key');
        if (state.sort.key === key) {
          state.sort.dir = state.sort.dir === 'desc' ? 'asc' : 'desc';
        } else {
          state.sort = { key: key, dir: key === 'latency' ? 'asc' : 'desc' };
        }
        renderBoard();
        var again = $('#board .sort[data-key="' + key + '"]');
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
  }

  function openFromHash() {
    var h = location.hash.replace(/^#/, '');
    if (!h || h.indexOf('entry-') !== 0) return;
    var row = $('#board tr.row[data-id="' + h + '"]');
    if (!row) return;
    toggleRow(h, true);
    row.scrollIntoView({ block: 'start' });
  }

  /* ---------- tests ---------- */

  function testCard(t) {
    var src = safeUrl(t.source_url);
    var types = (t.types || []).map(function (x) { return '<code>' + esc(x) + '</code>'; }).join(' ');
    return '<article class="card test" id="test-' + esc(t.name) + '">' +
      '<header><h4>' + esc(t.title || t.name) + '</h4><code class="tid">' + esc(t.name) + '</code></header>' +
      '<p>' + esc(t.description || '') + '</p>' +
      '<dl class="facts-grid">' +
      '<div><dt>Requests</dt><dd>' + fmtInt(t.requests) + '</dd></div>' +
      '<div><dt>Fields</dt><dd>' + fmtInt(t.fields) + '</dd></div>' +
      '<div><dt>Null share</dt><dd>' + fmtShare(t.null_share) + '</dd></div>' +
      '<div><dt>Metric</dt><dd>' + esc(t.metric || '—') + '</dd></div>' +
      '<div class="wide"><dt>Field types</dt><dd>' + (types || '—') + '</dd></div>' +
      '<div><dt>Licence</dt><dd>' + esc(t.license || '—') + '</dd></div>' +
      '<div><dt>Source</dt><dd>' + (src ? '<a href="' + esc(src) + '" rel="noopener">' + esc(hostOf(src)) + '</a>' : '—') + '</dd></div>' +
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
      return '<div class="area"><h3>' + esc(a) + ' <span class="count">' + plural(ts.length, 'test') + '</span></h3>' +
        '<div class="tests-grid">' + ts.map(testCard).join('') + '</div></div>';
    }).join('');
    host.innerHTML = html || '<div class="card empty"><p>No tests listed in the board file.</p></div>';

    var requests = tests.reduce(function (s, t) { return s + (isNum(t.requests) ? t.requests : 0); }, 0);
    var fieldsKnown = tests.length && tests.every(function (t) { return isNum(t.fields); });
    var fields = tests.reduce(function (s, t) { return s + (isNum(t.fields) ? t.fields : 0); }, 0);
    var meta = plural(tests.length, 'test') + ' in ' + plural(areas.length, 'area') + ', ' + fmtInt(requests) + ' requests' +
      (fieldsKnown ? ', ' + fmtInt(fields) + ' fields' : '');
    setText('[data-tests-meta]', meta + '. Public sources, pinned revisions, fixed seed.');
    setText('[data-facts]', 'Edition ' + (board.edition || '') + ': ' + meta + '.');
  }

  /* ---------- page ---------- */

  function renderMeta() {
    var board = state.board;
    if (board.edition) setText('[data-edition]', board.edition);
    setText('[data-test-count]', String((board.tests || []).length || 7));
    var gen = fmtDate(board.generated_utc);
    setText('[data-generated]', gen);
    var g = prepareEntries(board);
    var ranked = g.one.filter(function (e) { return isNum(e.index); }).length;
    var bits = [];
    if (ranked) bits.push(ranked + (ranked === 1 ? ' ranked entry' : ' ranked entries'));
    if (g.two.length) bits.push(plural(g.two.length, 'reference row'));
    var lead = bits.length ? bits.join(', ') + ', generated ' : 'Generated ';
    lead = lead.replace(/^./, function (c) { return c.toUpperCase(); });
    $all('[data-board-meta]').forEach(function (el) {
      el.innerHTML = esc(lead) + '<span class="nowrap">' + esc(gen) + '</span>';
    });
  }

  function showError(msg) {
    var host = $('#board');
    host.setAttribute('aria-busy', 'false');
    host.innerHTML = '<div class="error"><h3>Could not load the board</h3><p class="muted">' + esc(msg) + ' The file <code>data/board.json</code> is generated by <code>python -m extract_index board</code>.</p></div>';
  }

  function init() {
    renderJsonExamples();
    bindBoardEvents();
    renderDiagram(true);

    fetch(BOARD_URL, { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + BOARD_URL + '.'); return r.json(); })
      .then(function (board) {
        if (!board || typeof board !== 'object') throw new Error('The board file is not a JSON object.');
        state.board = board;
        renderMeta();
        renderBoard();
        renderTests();
        renderDiagram(true);
        openFromHash();
      })
      .catch(function (err) { showError(err && err.message ? err.message : String(err)); });

    var t;
    window.addEventListener('resize', function () {
      clearTimeout(t);
      t = setTimeout(function () { renderDiagram(false); syncScrollerWidth(); }, 120);
    });
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { renderDiagram(true); });
    }
    window.addEventListener('hashchange', openFromHash);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
