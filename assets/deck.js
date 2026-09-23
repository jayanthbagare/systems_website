/* Seeing the System — slideshow engine.
   Loads the slides listed in slides/manifest.js, scales them to the window,
   and handles navigation, themes, overview, notes and a presenter view. */
(() => {
  'use strict';

  const W = 1920, H = 1080;
  const params = new URLSearchParams(location.search);
  const isPresenter = params.has('presenter');
  const root = document.documentElement;
  const $ = (s, el = document) => el.querySelector(s);

  const stage = $('#stage');
  const countEl = $('#count');
  const progress = $('#progress');
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('seeing-the-system') : null;

  let all = [];          // every loaded <section>, in manifest order
  let list = [];         // the slides currently in the show (hidden ones excluded unless toggled)
  let index = 0;
  let showHidden = params.has('all');

  /* ---------- storage (optional; ignored when unavailable) ---------- */
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  /* ---------- palette & light/dark ---------- */
  // Each palette has a light and a dark mode; colours live in assets/deck.css.
  const PALETTES = [
    { id: 'terracotta', name: 'Terracotta', note: 'as designed',
      light: ['#FAF7F0', '#F0E9DC', '#D97757'], dark: ['#1C1A17', '#2A2622', '#C9967F'] },
    { id: 'sage', name: 'Sage',
      light: ['#F7F7F2', '#E7EBE0', '#4E7C5B'], dark: ['#161A17', '#232A25', '#9BC4A2'] },
    { id: 'indigo', name: 'Indigo',
      light: ['#F7F7FA', '#E7E9F2', '#4C57A8'], dark: ['#13151D', '#1F2331', '#A0AAF0'] },
    { id: 'graphite', name: 'Graphite',
      light: ['#F8F8F7', '#E9EAE8', '#1F7A78'], dark: ['#151617', '#222426', '#74C6C1'] },
  ];
  const look = { palette: 'terracotta', theme: 'light' };

  function applyLook(changes, fromRemote) {
    Object.assign(look, changes);
    if (!PALETTES.some(p => p.id === look.palette)) look.palette = 'terracotta';
    if (look.theme !== 'dark') look.theme = 'light';
    root.dataset.palette = look.palette;
    root.dataset.theme = look.theme;
    root.dataset.look = `${look.palette}-${look.theme}`;
    store.set('deck-palette', look.palette);
    store.set('deck-theme', look.theme);
    updateLetterbox();
    renderPaletteMenu();
    if (!fromRemote && channel) channel.postMessage({ type: 'look', palette: look.palette, theme: look.theme });
  }
  const toggleTheme = () => applyLook({ theme: look.theme === 'dark' ? 'light' : 'dark' });
  function cyclePalette(step = 1) {
    const i = PALETTES.findIndex(p => p.id === look.palette);
    const p = PALETTES[(i + step + PALETTES.length) % PALETTES.length];
    applyLook({ palette: p.id });
    flash(`${p.name}, ${look.theme}`);
  }

  const paletteMenu = $('#palette-menu');
  function renderPaletteMenu() {
    if (!paletteMenu) return;
    paletteMenu.innerHTML = '<p>Palette</p>' + PALETTES.map(p => {
      const sw = p[look.theme].map(c => `<i style="background:${c}"></i>`).join('');
      return `<button role="menuitemradio" aria-checked="${p.id === look.palette}" data-palette="${p.id}">
        <span class="swatch">${sw}</span><span>${p.name}${p.note ? ` <small style="opacity:.6">${p.note}</small>` : ''}</span></button>`;
    }).join('') +
    `<button class="mode" data-mode>${look.theme === 'dark' ? 'Switch to light' : 'Switch to dark'} <small style="opacity:.6;margin-left:auto">T</small></button>`;
  }
  function togglePaletteMenu(force) {
    const on = paletteMenu.classList.toggle('on', force);
    if (on) paletteMenu.querySelector('[aria-checked="true"]')?.focus();
  }
  paletteMenu?.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.palette) applyLook({ palette: b.dataset.palette });
    else if (b.hasAttribute('data-mode')) toggleTheme();
  });

  /* ---------- load slides ---------- */
  async function load() {
    const manifest = (window.DECK_MANIFEST || []).map(e => (typeof e === 'string' ? { file: e } : e));
    if (!manifest.length) return fail('No slides listed', 'Add slide files to <code>slides/manifest.js</code>.');
    let texts;
    try {
      texts = await Promise.all(manifest.map(e =>
        fetch('slides/' + e.file).then(r => {
          if (!r.ok) throw new Error(`slides/${e.file} returned ${r.status}`);
          return r.text();
        })));
    } catch (err) {
      if (location.protocol === 'file:') {
        return fail('Open this deck through a web server',
          'Browsers block slides from loading off the file system. In this folder run ' +
          '<code>python3 -m http.server 8000</code> and open <code>http://localhost:8000</code>, ' +
          'or deploy the folder to Netlify or GitHub Pages.');
      }
      return fail('A slide failed to load', String(err.message) + '. Check the file name in <code>slides/manifest.js</code>.');
    }
    const tpl = document.createElement('template');
    texts.forEach((txt, i) => {
      tpl.innerHTML = txt;
      const sec = tpl.content.querySelector('section.slide');
      if (!sec) { console.warn('No <section class="slide"> in', manifest[i].file); return; }
      sec.dataset.file = manifest[i].file;
      sec.dataset.hidden = manifest[i].hidden ? 'true' : 'false';
      if (!sec.dataset.title) sec.dataset.title = (sec.querySelector('h1,h2')?.textContent || manifest[i].file).trim();
      stage.appendChild(sec);
      all.push(sec);
    });
    rebuildList();
    const start = parseHash();
    go(start == null ? 0 : start, { silent: true });
    if (isPresenter) initPresenter();
  }

  function fail(title, body) {
    document.body.insertAdjacentHTML('beforeend', `<div class="message"><div><h1>${title}</h1><p>${body}</p></div></div>`);
  }

  function rebuildList() {
    const current = list[index];
    list = all.filter(s => showHidden || s.dataset.hidden !== 'true');
    const at = current ? list.indexOf(current) : -1;
    index = at >= 0 ? at : Math.min(index, list.length - 1);
  }

  /* ---------- navigation ---------- */
  function parseHash() {
    const m = location.hash.match(/^#\/(\d+)/);
    return m ? Math.max(0, parseInt(m[1], 10) - 1) : null;
  }

  function go(i, opts = {}) {
    if (!list.length) return;
    i = Math.max(0, Math.min(list.length - 1, i));
    const prev = list[index];
    if (prev) prev.classList.remove('active');
    index = i;
    const cur = list[index];
    cur.classList.add('active');
    countEl.textContent = `${index + 1} / ${list.length}`;
    progress.style.width = `${((index + 1) / list.length) * 100}%`;
    const h = `#/${index + 1}`;
    if (location.hash !== h) history.replaceState(null, '', h);
    document.title = `${cur.dataset.title} · Seeing the System`;
    updateLetterbox();
    updateNotes();
    if (isPresenter) renderPresenter();
    if (!opts.remote && channel) channel.postMessage({ type: 'go', file: cur.dataset.file, index });
  }
  const next = () => go(index + 1);
  const prev = () => go(index - 1);

  function updateLetterbox() {
    const cur = list[index];
    if (!cur || isPresenter) return;
    document.body.style.setProperty('--letterbox', getComputedStyle(cur).backgroundColor);
  }

  /* ---------- scaling ---------- */
  function fit() {
    const s = Math.min(innerWidth / W, innerHeight / H);
    stage.style.setProperty('--scale', s);
    if (isPresenter) renderPresenter();
  }
  addEventListener('resize', fit);
  fit();

  /* ---------- fullscreen ---------- */
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else document.documentElement.requestFullscreen?.().catch(() => {});
  }

  /* ---------- clone a slide into a thumbnail frame ---------- */
  function thumbInto(frame, slide) {
    frame.innerHTML = '';
    if (!slide) return;
    const c = slide.cloneNode(true);
    c.classList.remove('active');
    c.removeAttribute('id');
    frame.appendChild(c);
    const w = frame.clientWidth || 240;
    c.style.transform = `scale(${w / W})`;
  }

  /* ---------- overview ---------- */
  const overview = $('#overview');
  const ovGrid = $('#ov-grid');
  function openOverview() {
    ovGrid.innerHTML = '';
    list.forEach((s, i) => {
      const b = document.createElement('button');
      b.className = 'ov-tile' + (i === index ? ' current' : '') + (s.dataset.hidden === 'true' ? ' is-hidden' : '');
      b.innerHTML = `<div class="ov-thumb"></div><div class="ov-label"><b>${i + 1}</b><span></span></div>`;
      b.querySelector('span').textContent = s.dataset.title;
      b.addEventListener('click', () => { closeOverlays(); go(i); });
      ovGrid.appendChild(b);
    });
    overview.classList.add('on');
    requestAnimationFrame(() => {
      ovGrid.querySelectorAll('.ov-thumb').forEach((f, i) => thumbInto(f, list[i]));
      const cur = ovGrid.children[index];
      cur?.scrollIntoView({ block: 'center' });
      cur?.focus({ preventScroll: true });
    });
  }

  /* ---------- notes & help ---------- */
  const notesPanel = $('#notes');
  function notesHTML(slide) {
    const n = slide?.querySelector('aside.notes');
    return n && n.textContent.trim() ? n.innerHTML : '<p class="empty">No speaker notes for this slide.</p>';
  }
  function updateNotes() { if (notesPanel.classList.contains('on')) notesPanel.innerHTML = notesHTML(list[index]); }
  function toggleNotes() { notesPanel.classList.toggle('on'); updateNotes(); }

  const help = $('#help');
  function closeOverlays() {
    const wasOpen = overview.classList.contains('on') || help.classList.contains('on');
    overview.classList.remove('on');
    help.classList.remove('on');
    return wasOpen;
  }

  function toggleHidden() {
    showHidden = !showHidden;
    rebuildList();
    go(index);
    flash(showHidden ? `Showing hidden slides (${list.length} total)` : `Hidden slides skipped (${list.length} in the show)`);
  }

  /* ---------- small transient message ---------- */
  const jump = $('#jump');
  let jumpBuf = '', jumpTimer;
  function flash(text, ms = 1600) {
    jump.textContent = text;
    jump.classList.add('on');
    clearTimeout(jumpTimer);
    jumpTimer = setTimeout(() => { jump.classList.remove('on'); jumpBuf = ''; }, ms);
  }

  /* ---------- keyboard ---------- */
  const blackout = $('#blackout');
  addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (/^[0-9]$/.test(k)) { jumpBuf += k; flash(`Go to slide ${jumpBuf}`, 1800); return; }
    if (k === 'Enter' && jumpBuf) { go(parseInt(jumpBuf, 10) - 1); jumpBuf = ''; jump.classList.remove('on'); e.preventDefault(); return; }
    if (overview.classList.contains('on') && k !== 'Escape' && k !== 'o' && k !== 'O') return;
    switch (k) {
      case 'ArrowRight': case 'ArrowDown': case 'PageDown': case ' ': case 'Enter':
        e.preventDefault(); if (blackout.classList.contains('on')) blackout.classList.remove('on'); else next(); break;
      case 'ArrowLeft': case 'ArrowUp': case 'PageUp': case 'Backspace':
        e.preventDefault(); prev(); break;
      case 'Home': go(0); break;
      case 'End': go(list.length - 1); break;
      case 'f': case 'F': toggleFullscreen(); break;
      case 't': case 'T': toggleTheme(); break;
      case 'c': case 'C': cyclePalette(e.shiftKey ? -1 : 1); break;
      case 'o': case 'O': overview.classList.contains('on') ? closeOverlays() : openOverview(); break;
      case 'Escape': if (paletteMenu.classList.contains('on')) togglePaletteMenu(false); else if (!closeOverlays()) notesPanel.classList.remove('on'); break;
      case 'n': case 'N': toggleNotes(); break;
      case 'p': case 'P': openPresenter(); break;
      case 'b': case 'B': case '.': blackout.classList.toggle('on'); break;
      case 'h': case 'H': toggleHidden(); break;
      case '?': help.classList.toggle('on'); break;
    }
  });

  /* ---------- buttons ---------- */
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-action]');
    if (!a) { if (!e.target.closest('#palette-menu')) paletteMenu?.classList.remove('on'); return; }
    if (a.dataset.action !== 'palette') paletteMenu?.classList.remove('on');
    ({ prev, next, theme: toggleTheme, palette: () => togglePaletteMenu(), overview: openOverview, fullscreen: toggleFullscreen,
       notes: toggleNotes, presenter: openPresenter, help: () => help.classList.toggle('on'),
       close: closeOverlays })[a.dataset.action]?.();
  });
  help.addEventListener('click', e => { if (e.target === help) closeOverlays(); });

  /* ---------- touch ---------- */
  let tx = null, ty = null;
  addEventListener('touchstart', e => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; }, { passive: true });
  addEventListener('touchend', e => {
    if (tx == null || overview.classList.contains('on')) return;
    const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) (dx < 0 ? next : prev)();
    tx = ty = null;
  });

  /* ---------- idle: hide cursor & controls while presenting ---------- */
  let idleTimer;
  function wake() {
    document.body.classList.remove('idle');
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (!paletteMenu?.classList.contains('on')) document.body.classList.add('idle'); }, 2500);
  }
  addEventListener('mousemove', wake);
  wake();

  addEventListener('hashchange', () => { const i = parseHash(); if (i != null && i !== index) go(i); });

  /* ---------- sync between audience window and presenter ---------- */
  channel?.addEventListener('message', ({ data }) => {
    if (data.type === 'go') {
      const i = list.findIndex(s => s.dataset.file === data.file);
      if (i >= 0 && i !== index) go(i, { remote: true });
    } else if (data.type === 'look') {
      applyLook({ palette: data.palette, theme: data.theme }, true);
    } else if (data.type === 'hello' && !isPresenter) {
      channel.postMessage({ type: 'go', file: list[index]?.dataset.file, index });
      channel.postMessage({ type: 'look', palette: look.palette, theme: look.theme });
    }
  });

  function openPresenter() {
    const url = location.pathname + '?presenter' + (showHidden ? '&all' : '') + location.hash;
    window.open(url, 'seeing-the-system-presenter', 'width=1280,height=800');
  }

  /* ---------- presenter view ---------- */
  let t0 = Date.now(), paused = false, pausedAt = 0;
  function initPresenter() {
    document.body.classList.add('presenter');
    document.body.insertAdjacentHTML('beforeend', `
      <div class="pv">
        <div class="pv-bar">
          <span class="pv-time" id="pv-time">0:00</span>
          <button id="pv-pause">Pause timer</button><button id="pv-reset">Reset</button>
          <span class="pv-clock" id="pv-clock"></span>
          <span class="pv-count" id="pv-count"></span>
          <button data-action="prev" aria-label="Previous slide">Previous</button>
          <button data-action="next" aria-label="Next slide">Next</button>
          <button data-action="theme">Light / dark</button><button id="pv-palette">Palette</button>
        </div>
        <div class="pv-main"><div class="pv-frame" id="pv-cur"></div><div class="pv-label" id="pv-title"></div></div>
        <div class="pv-side">
          <div><div class="pv-label">Next</div><div class="pv-frame" id="pv-next"></div></div>
          <div class="pv-notes" id="pv-notes"></div>
        </div>
      </div>`);
    $('#pv-pause').onclick = e => {
      paused = !paused;
      if (paused) pausedAt = Date.now(); else t0 += Date.now() - pausedAt;
      e.target.textContent = paused ? 'Resume timer' : 'Pause timer';
    };
    $('#pv-palette').onclick = () => cyclePalette();
    $('#pv-reset').onclick = () => { t0 = Date.now(); pausedAt = Date.now(); };
    setInterval(tick, 500);
    tick();
    channel?.postMessage({ type: 'hello' });
    renderPresenter();
  }
  function tick() {
    const ms = (paused ? pausedAt : Date.now()) - t0;
    const s = Math.floor(ms / 1000);
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = String(s % 60).padStart(2, '0');
    $('#pv-time').textContent = hh ? `${hh}:${String(mm).padStart(2, '0')}:${ss}` : `${mm}:${ss}`;
    $('#pv-clock').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  function renderPresenter() {
    const cur = $('#pv-cur');
    if (!cur || !list.length) return;
    thumbInto(cur, list[index]);
    thumbInto($('#pv-next'), list[index + 1]);
    if (!list[index + 1]) $('#pv-next').innerHTML = '<div class="message" style="position:absolute;font-size:16px">End of deck</div>';
    $('#pv-title').textContent = list[index].dataset.title;
    $('#pv-count').textContent = `${index + 1} / ${list.length}`;
    $('#pv-notes').innerHTML = notesHTML(list[index]);
  }

  applyLook({ palette: params.get('palette') || store.get('deck-palette') || 'terracotta',
              theme: params.get('theme') || store.get('deck-theme') || 'light' }, true);
  load();
})();
