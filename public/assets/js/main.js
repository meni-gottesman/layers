/* ============================================================================
   Layers Superfood Bar — site runtime (v2, multi-page)
   Progressive enhancement throughout: every page is readable and every link
   works with JS disabled. GSAP is optional; if it fails to load nothing hides.

   Hard-won resilience notes — do not "simplify" these away:
   - requestAnimationFrame is throttled to ZERO in background tabs, on bfcache
     restore and in low-power mode, which silently stops GSAP, ScrollTrigger
     AND IntersectionObserver. Anything that hides content must be recoverable
     by a plain timer, and anything that locks scroll must not depend on rAF.
   ========================================================================== */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var SQUARE_ORDER = 'https://layerssuperfoodbar.square.site';
  var PLACEHOLDER_FACE = '/assets/img/face.png';

  /* --------------------------------------------------------------------- */
  /* Focus trap + scroll lock (shared by drawer and item sheet)             */
  /* --------------------------------------------------------------------- */
  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

  function trapFocus(container, evt) {
    var nodes = $$(FOCUSABLE, container).filter(function (el) {
      return el.offsetParent !== null || el === document.activeElement;
    });
    if (!nodes.length) return;
    var first = nodes[0], last = nodes[nodes.length - 1];
    if (evt.shiftKey && document.activeElement === first) {
      evt.preventDefault(); last.focus();
    } else if (!evt.shiftKey && document.activeElement === last) {
      evt.preventDefault(); first.focus();
    }
  }

  var lockCount = 0, savedScrollY = 0;
  function lockScroll() {
    if (lockCount++ === 0) {
      savedScrollY = window.scrollY;
      document.body.style.position = 'fixed';
      document.body.style.top = -savedScrollY + 'px';
      document.body.style.width = '100%';
    }
  }
  function unlockScroll() {
    if (lockCount > 0 && --lockCount === 0) {
      document.body.style.position = '';
      document.body.style.top = '';
      document.body.style.width = '';
      window.scrollTo(0, savedScrollY);
    }
  }

  /* --------------------------------------------------------------------- */
  /* 1 · Header. Home: transparent over hero -> solid on scroll.            */
  /*     Every other page (.header--static): solid from the top, no logic.  */
  /* --------------------------------------------------------------------- */
  function initHeader() {
    var header = $('#site-header');
    if (!header || header.classList.contains('header--static')) return;

    var solid = null;
    function setSolid(next) {
      if (next === solid) return;
      solid = next;
      header.setAttribute('data-state', next ? 'solid' : 'transparent');
    }
    setSolid(false);

    var sentinel = $('#hdr-sentinel');
    if (sentinel && 'IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        setSolid(!entries[0].isIntersecting);
      }, { threshold: 0 }).observe(sentinel);
    }

    // Belt and braces: IO callbacks ride the rendering steps, so a stalled rAF
    // strands the header. The scroll fallback runs always, with a timer backup.
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      var run = function () {
        setSolid((window.scrollY || document.documentElement.scrollTop || 0) > 60);
        ticking = false;
      };
      if (window.requestAnimationFrame) window.requestAnimationFrame(run);
      window.setTimeout(function () { if (ticking) run(); }, 120);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('pageshow', onScroll);
    onScroll();
  }

  /* --------------------------------------------------------------------- */
  /* 2 · Mobile drawer                                                      */
  /* --------------------------------------------------------------------- */
  function initDrawer() {
    var burger = $('#m-burger'), drawer = $('#m-drawer'),
        scrim  = $('#m-scrim'),  close  = $('#m-close');
    if (!burger || !drawer || !scrim) return;

    var open = false, lastFocus = null;

    function setOpen(next) {
      if (next === open) return;
      open = next;

      if (next) {
        lastFocus = document.activeElement;
        drawer.hidden = false; scrim.hidden = false;
        // Forced synchronous reflow, deliberately NOT rAF: with rAF dead the
        // drawer would lock scroll and trap focus while staying off-screen.
        void drawer.offsetWidth;
        drawer.setAttribute('data-open', '');
        scrim.setAttribute('data-open', '');
        drawer.setAttribute('aria-hidden', 'false');
        burger.setAttribute('aria-expanded', 'true');
        burger.setAttribute('aria-label', 'Close menu');
        lockScroll();
        if (close) close.focus();
      } else {
        drawer.removeAttribute('data-open');
        scrim.removeAttribute('data-open');
        drawer.setAttribute('aria-hidden', 'true');
        burger.setAttribute('aria-expanded', 'false');
        burger.setAttribute('aria-label', 'Open menu');
        unlockScroll();
        window.setTimeout(function () {
          if (!open) { drawer.hidden = true; scrim.hidden = true; }
        }, 340);
        if (lastFocus) lastFocus.focus();
      }
    }

    burger.addEventListener('click', function () { setOpen(!open); });
    if (close) close.addEventListener('click', function () { setOpen(false); });
    scrim.addEventListener('click', function () { setOpen(false); });
    $$('[data-drawer]', drawer).forEach(function (a) {
      a.addEventListener('click', function () { setOpen(false); });
    });
    document.addEventListener('keydown', function (e) {
      if (!open) return;
      if (e.key === 'Escape') setOpen(false);
      else if (e.key === 'Tab') trapFocus(drawer, e);
    });

    if (window.matchMedia) {
      var mq = window.matchMedia('(min-width:1101px)');
      var onChange = function (e) { if (e.matches) setOpen(false); };
      if (mq.addEventListener) mq.addEventListener('change', onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
  }

  /* --------------------------------------------------------------------- */
  /* 3 · Item detail sheet (menu page)                                      */
  /* --------------------------------------------------------------------- */
  var sheet = null, sheetOpen = false, sheetLastFocus = null;

  function openSheet(item) {
    if (!sheet) return;
    sheetLastFocus = document.activeElement;

    var media = $('[data-sheet-media]', sheet);
    media.innerHTML = '';
    media.classList.toggle('sheet__media--small', !!item.image_small);
    if (item.image) {
      var img = document.createElement('img');
      img.src = item.image; img.alt = item.name || '';
      img.width = 800; img.height = 800;
      media.appendChild(img);
    } else {
      var ph = document.createElement('div');
      ph.className = 'menu-card__media--ph';
      ph.innerHTML = '<img src="' + PLACEHOLDER_FACE + '" alt="" width="88" height="88">';
      media.appendChild(ph);
    }

    $('[data-sheet-kind]', sheet).textContent = item.kind || '';
    $('[data-sheet-name]', sheet).textContent = item.name || '';
    $('[data-sheet-note]', sheet).textContent = item.note || '';
    var priceEl = $('[data-sheet-price]', sheet);
    priceEl.textContent = item.price ? money(item.price) : '';
    var calEl = $('[data-sheet-cal]', sheet);
    calEl.textContent = item.calories ? item.calories + ' cal' : (item.soldOut ? 'Sold out' : '');

    // Details come verbatim from the shop's own Square descriptions. Built
    // with textContent only — nothing from the data is parsed as HTML.
    var tags = $('[data-sheet-tags]', sheet);
    tags.innerHTML = '';
    (Array.isArray(item.highlights) ? item.highlights : []).forEach(function (t) {
      var li = document.createElement('li'); li.textContent = t; tags.appendChild(li);
    });
    var facts = $('[data-sheet-facts]', sheet);
    facts.innerHTML = '';
    [['Base', item.base], ['Toppings', item.toppings], ['Ingredients', item.ingredients]].forEach(function (row) {
      if (!Array.isArray(row[1]) || !row[1].length) return;
      var dt = document.createElement('dt'); dt.textContent = row[0];
      var dd = document.createElement('dd'); dd.textContent = row[1].join(', ');
      facts.appendChild(dt); facts.appendChild(dd);
    });
    var mac = item.macros || {}, parts = [];
    ['protein', 'fiber', 'sugar'].forEach(function (k) {
      if (typeof mac[k] === 'number') parts.push(k.charAt(0).toUpperCase() + k.slice(1) + ' ' + mac[k] + 'g');
    });
    $('[data-sheet-macros]', sheet).textContent = parts.join(' · ');
    var al = $('[data-sheet-allergens]', sheet);
    al.innerHTML = '';
    (Array.isArray(item.allergens) ? item.allergens : []).forEach(function (t) {
      var p = document.createElement('p'); p.textContent = t; al.appendChild(p);
    });

    var order = $('[data-sheet-order]', sheet);
    var cat = /^[A-Z0-9]{8,40}$/.test(item.category_id || '') ? item.category_id : '';
    order.href = SQUARE_ORDER + (cat ? '/#' + cat : '');   // the store scrolls to #<category id>
    order.setAttribute('aria-label', 'Order ' + (item.name || 'item') + ' on Square (opens in a new tab)');
    order.style.display = item.soldOut ? 'none' : '';

    sheet.hidden = false; sheetOpen = true;
    void sheet.offsetWidth;                    // same rAF-free open as the drawer
    sheet.setAttribute('data-open', '');
    lockScroll();
    var closeBtn = $('[data-sheet-close]', sheet);
    if (closeBtn && closeBtn.focus) $('.sheet__close', sheet).focus();
  }

  function closeSheet() {
    if (!sheet || !sheetOpen) return;
    sheetOpen = false;
    sheet.removeAttribute('data-open');
    unlockScroll();
    window.setTimeout(function () { if (!sheetOpen) sheet.hidden = true; }, 330);
    if (sheetLastFocus) sheetLastFocus.focus();
  }

  function initSheet() {
    sheet = $('#item-sheet');
    if (!sheet) return;
    $$('[data-sheet-close]', sheet).forEach(function (el) {
      el.addEventListener('click', closeSheet);
    });
    document.addEventListener('keydown', function (e) {
      if (!sheetOpen) return;
      if (e.key === 'Escape') closeSheet();
      else if (e.key === 'Tab') trapFocus($('.sheet__panel', sheet), e);
    });

    // Delegated: works for the static fallback markup and live-synced cards.
    var root = $('[data-menu-root]');
    if (root) {
      root.addEventListener('click', function (e) {
        var btn = e.target.closest('.menu-card__open');
        if (!btn) return;
        var card = btn.closest('.menu-card');
        if (!card || !card.dataset.item) return;
        try { openSheet(JSON.parse(card.dataset.item)); } catch (err) {}
      });
    }
  }

  /* --------------------------------------------------------------------- */
  /* 4 · Category chip rail: scroll-spy                                     */
  /* --------------------------------------------------------------------- */
  function spyChips() {
    var sections = $$('[data-cat-section]');
    if (!sections.length) return;
    function update() {
      var line = (window.innerHeight || 800) * 0.32;
      var current = sections[0];
      sections.forEach(function (sec) {
        if (sec.getBoundingClientRect().top <= line) current = sec;
      });
      $$('[data-chip]').forEach(function (chip) {
        var active = chip.getAttribute('data-chip') === current.id;
        chip.classList.toggle('chip--active', active);
        if (active) chip.setAttribute('aria-current', 'true');
        else chip.removeAttribute('aria-current');
      });
    }
    window.addEventListener('scroll', function () {
      window.setTimeout(update, 80);           // timer, not rAF — see header note
    }, { passive: true });
    update();
  }

  /* --------------------------------------------------------------------- */
  /* 5 · Live menu from Square (menu page only)                             */
  /* --------------------------------------------------------------------- */
  function money(v) {
    var n = typeof v === 'number' ? v : parseFloat(v);
    return isNaN(n) ? '' : '$' + n.toFixed(2);
  }

  function safeImageSrc(value) {
    if (typeof value !== 'string') return null;
    var v = value.trim();
    if (!v) return null;
    if (v.charAt(0) === '/') return v;
    if (/^https?:\/\//i.test(v)) return v;
    return null;
  }

  function slugify(name) {
    return 'cat-' + String(name || 'menu').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }


  /* A card for an item that is live on Square but not in the curated menu
     (a new launch). Same markup the build emits; photo from Square if any. */
  function buildCard(item) {
    var card = document.createElement('article');
    card.className = 'menu-card';
    if (item.id) card.setAttribute('data-id', item.id);
    if (item.soldOut) card.setAttribute('data-sold-out', '');
    card.dataset.item = JSON.stringify({
      kind: item.kind || '', name: item.name || '', note: item.note || '',
      price: item.price, calories: item.calories,
      image: safeImageSrc(item.image), soldOut: !!item.soldOut
    });

    var open = document.createElement('button');
    open.type = 'button';
    open.className = 'menu-card__open';
    open.setAttribute('aria-label', (item.name || 'Item') + ' — details');

    var media = document.createElement('span');
    media.className = 'menu-card__media';
    var src = safeImageSrc(item.image);
    function placeholder() {
      media.className = 'menu-card__media menu-card__media--ph';
      media.innerHTML = '<img src="' + PLACEHOLDER_FACE + '" alt="" width="88" height="88">';
    }
    if (src) {
      var img = document.createElement('img');
      img.src = src; img.alt = ''; img.loading = 'lazy'; img.decoding = 'async';
      img.width = 800; img.height = 800;
      img.addEventListener('error', function handle() { img.removeEventListener('error', handle); placeholder(); });
      media.appendChild(img);
    } else {
      placeholder();
    }

    var body = document.createElement('span');
    body.className = 'menu-card__body';
    var name = document.createElement('span');
    name.className = 'menu-card__name';
    name.textContent = item.name || '';
    body.appendChild(name);
    if (item.note) {
      var note = document.createElement('span');
      note.className = 'menu-card__note';
      note.textContent = item.note;
      body.appendChild(note);
    }
    var meta = document.createElement('span');
    meta.className = 'menu-card__meta';
    body.appendChild(meta);
    open.appendChild(media); open.appendChild(body);
    card.appendChild(open);
    setCardMeta(card, item);
    return card;
  }

  function setCardMeta(card, item) {
    var meta = $('.menu-card__meta', card);
    if (!meta) return;
    meta.innerHTML = '';
    if (item.price != null && item.price !== '') {
      var price = document.createElement('span');
      price.className = 'menu-card__price';
      price.textContent = money(item.price);
      meta.appendChild(price);
    }
    if (item.calories) {
      var cal = document.createElement('span');
      cal.className = 'menu-card__cal';
      cal.textContent = item.calories + ' cal';
      meta.appendChild(cal);
    }
    if (item.soldOut) {
      var so = document.createElement('span');
      so.className = 'menu-card__sold';
      so.textContent = 'Sold out';
      meta.appendChild(so);
    }
  }

  /* The build ships the curated menu (sharp studio photos, ingredients,
     nutrition). When Square is connected, live data only updates what can
     change during the day — sold-out, a brand-new item — so the curated photos
     and details are never replaced by Square's thumbnails. Prices come from
     tools/sync-menu-from-store.py, which reads the price the store shows
     (including the required +$0.25 option the Catalog API leaves out). */
  function initMenu() {
    var root = $('[data-menu-page]');
    if (!root) return;
    var statusEl = $('[data-menu-status]'), dot = $('[data-menu-dot]');

    function markCached() {
      if (dot) dot.setAttribute('data-state', 'stale');
    }

    fetch('/api/menu', { headers: { accept: 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('menu ' + r.status); return r.json(); })
      .then(function (data) {
        if (!data || !Array.isArray(data.categories) || !data.categories.length) return;
        if (data.source === 'fallback') { markCached(); return; }

        // Items hidden on the site (content/menu.json) stay hidden even though
        // Square still lists them: the build names them in data-hidden-ids.
        var hidden = (root.getAttribute('data-hidden-ids') || '').split(/\s+/).filter(Boolean);
        var changed = false;
        data.categories.forEach(function (cat) {
          (cat.items || []).forEach(function (it) {
            if (it.id && hidden.indexOf(String(it.id)) !== -1) return;
            var card = it.id ? root.querySelector('.menu-card[data-id="' + String(it.id).replace(/"/g, '') + '"]') : null;
            if (card) {
              var cur = {};
              try { cur = JSON.parse(card.dataset.item || '{}'); } catch (e) {}
              cur.soldOut = !!it.soldOut;
              card.dataset.item = JSON.stringify(cur);
              if (it.soldOut) card.setAttribute('data-sold-out', ''); else card.removeAttribute('data-sold-out');
              setCardMeta(card, cur);
              return;
            }
            // New on Square: add it to the matching section (by name), if any.
            var sec = root.querySelector('#' + slugify(cat.name)) ||
                      root.querySelector('#' + slugify(String(cat.name || '').replace(/^layers\s+/i, '')));
            var grid = sec && $('.menu-grid', sec);
            if (grid) { grid.appendChild(buildCard(it)); changed = true; }
          });
        });
        if (dot) dot.setAttribute('data-state', 'live');
        if (statusEl) statusEl.textContent = 'Live from Square. Prices and availability are confirmed when you order.';
        if (changed) {
          document.dispatchEvent(new CustomEvent('layers:menu-rendered'));
          if (window.gsap && window.ScrollTrigger) window.ScrollTrigger.refresh();
        }
      })
      .catch(markCached);   // Square unreachable — the curated menu stays as built

    spyChips();
  }

  /* --------------------------------------------------------------------- */
  /* 6 · Open-now line + hours table                                        */
  /*     Hours: from <meta name="layers-hours">, America/Los_Angeles.        */
  /* --------------------------------------------------------------------- */
  function shopClock() {
    try {
      var parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/Los_Angeles',
        weekday: 'short', hour: 'numeric', hour12: false, minute: 'numeric',
        year: 'numeric', month: '2-digit', day: '2-digit'
      }).formatToParts(new Date());
      var get = function (t) {
        var p = parts.filter(function (x) { return x.type === t; })[0];
        return p ? p.value : null;
      };
      var dowMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
      return {
        dow: dowMap[get('weekday')],
        // some engines say "24" for midnight with hour12:false
        mins: (parseInt(get('hour'), 10) % 24) * 60 + parseInt(get('minute'), 10),
        ymd: get('year') + '-' + get('month') + '-' + get('day')     // the shop's date, YYYY-MM-DD
      };
    } catch (e) { return null; }
  }

  function addDays(ymd, n) {
    var p = String(ymd).split('-');
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + n)).toISOString().slice(0, 10);
  }

  /* --------------------------------------------------------------------- */
  /* 6b · Dated content. The daily build drops ended specials, past events  */
  /*      and special hours; until it runs, hide what has passed ([data-   */
  /*      until] = last day shown, YYYY-MM-DD in the shop's time zone).     */
  /* --------------------------------------------------------------------- */
  function initDated() {
    var els = $$('[data-until]');
    if (!els.length) return;
    var now = shopClock();
    if (!now || !/^\d{4}-\d{2}-\d{2}$/.test(now.ymd)) return;
    els.forEach(function (el) {
      if (el.getAttribute('data-until') < now.ymd) el.hidden = true;
    });
    // a row of specials down to ONE showing: lay it out as the build lays out
    // a single special (photo beside the text, capped width) instead of one
    // card stretched across the whole row, and tell the browser the photo's
    // real width (the build's sizes for one special) so it isn't upscaled
    $$('.specials--row').forEach(function (row) {
      var shown = $$('.special', row).filter(function (s) { return !s.hidden; });
      if (shown.length !== 1) return;
      row.classList.remove('specials--row');
      row.classList.add('specials--one');
      $$('source[sizes], img[sizes]', shown[0]).forEach(function (el) {
        el.setAttribute('sizes', '(max-width: 820px) 100vw, 40vw');
      });
    });
    // a block whose every entry has passed goes too (entries without an end
    // date never pass, so a band with an open-ended special stays)
    [['[data-special-hours]', 'tr'], ['.events', '.event'],
     ['.ed--specials, .menu-specials, .links__more', '.special, .event']].forEach(function (pair) {
      $$(pair[0]).forEach(function (box) {
        var items = $$(pair[1], box);
        if (items.length && items.every(function (r) { return r.hidden; })) box.hidden = true;
      });
    });
  }

  /* --------------------------------------------------------------------- */
  /* 6c · Announcement bar: dismiss, remembered per message. The bar's own  */
  /*      inline script already removed it if dismissed or out of date.     */
  /* --------------------------------------------------------------------- */
  function initAnnouncement() {
    var bar = $('#ann');
    if (!bar) return;
    var btn = $('[data-ann-close]', bar);
    if (!btn) return;
    btn.addEventListener('click', function () {
      try { window.localStorage.setItem('layers-ann-dismissed', bar.getAttribute('data-ann-key') || ''); } catch (e) {}
      var next = $('#main') || document.body;
      bar.parentNode.removeChild(bar);
      document.body.classList.remove('has-ann');
      // focus would otherwise fall back to the top of the document
      if (next && next.focus) { next.setAttribute('tabindex', '-1'); next.focus({ preventScroll: true }); }
    });
  }

  /* --------------------------------------------------------------------- */
  /* Order page: the Square store, embedded. ?c=<Square category id> opens  */
  /* the store at that category; only ids of the expected shape are used.   */
  /* --------------------------------------------------------------------- */
  function initOrderFrame() {
    var frame = $('#order-frame');
    if (!frame) return;
    var m = /[?&]c=([A-Z0-9]{8,40})(?:&|$)/.exec(window.location.search);
    if (!m) return;
    var url = SQUARE_ORDER.replace(/\/$/, '') + '/#' + m[1];   // the store scrolls to #<category id>
    frame.src = url;
    $$('[data-order-out]').forEach(function (a) { a.href = url; });
  }

  /* --------------------------------------------------------------------- */
  /* Albums: cover tiles open a full-screen viewer. Arrows / swipe to move,  */
  /* Esc to close; focus stays inside and returns to the tile on close.      */
  /* --------------------------------------------------------------------- */
  function initAlbums() {
    var dataEl = $('#albums-data'), viewer = $('#album-viewer');
    if (!dataEl || !viewer) return;
    var albums = {};
    try { JSON.parse(dataEl.textContent).forEach(function (a) { albums[a.slug] = a; }); } catch (e) { return; }
    var img = $('.viewer__img', viewer), source = $('source', viewer),
        title = $('#viewer-title'), count = $('.viewer__count', viewer),
        altEl = $('[data-viewer-alt]', viewer);
    var current = null, index = 0, lastFocus = null, touchX = null;

    function show(i) {
      var photos = current.photos;
      index = (i + photos.length) % photos.length;
      var p = photos[index];
      source.srcset = p.src + '.webp';
      img.src = p.src + '.jpg';
      img.width = p.w; img.height = p.h;
      img.alt = p.alt;
      altEl.textContent = p.alt;
      count.textContent = (index + 1) + ' / ' + photos.length;
      var next = photos[(index + 1) % photos.length];      // warm the next one
      if (next) { var pre = new Image(); pre.src = next.src + '.jpg'; }
    }
    function open(slug, from) {
      current = albums[slug];
      if (!current) return;
      lastFocus = from || document.activeElement;
      title.textContent = current.title;
      show(0);
      viewer.hidden = false;
      void viewer.offsetWidth;
      viewer.setAttribute('data-open', '');
      lockScroll();
      $('[data-viewer-close]', viewer).focus();
    }
    function close() {
      if (viewer.hidden) return;
      viewer.removeAttribute('data-open');
      viewer.hidden = true;
      unlockScroll();
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
    $$('[data-album]').forEach(function (tile) {
      tile.addEventListener('click', function () { open(tile.getAttribute('data-album'), tile); });
    });
    $('[data-viewer-close]', viewer).addEventListener('click', close);
    $('[data-viewer-prev]', viewer).addEventListener('click', function () { show(index - 1); });
    $('[data-viewer-next]', viewer).addEventListener('click', function () { show(index + 1); });
    viewer.addEventListener('click', function (e) { if (e.target === viewer || e.target.classList.contains('viewer__stage')) close(); });
    document.addEventListener('keydown', function (e) {
      if (viewer.hidden) return;
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowLeft') show(index - 1);
      else if (e.key === 'ArrowRight') show(index + 1);
      else if (e.key === 'Tab') trapFocus(viewer, e);
    });
    viewer.addEventListener('touchstart', function (e) { touchX = e.touches[0].clientX; }, { passive: true });
    viewer.addEventListener('touchend', function (e) {
      if (touchX === null) return;
      var dx = e.changedTouches[0].clientX - touchX; touchX = null;
      if (Math.abs(dx) > 40) show(index + (dx < 0 ? 1 : -1));
    });
  }

  function initOpenNow() {
    var els = $$('[data-open-now]');
    var table = $('[data-hours]');
    if (!els.length && !table) return;

    var now = shopClock();
    if (!now) return;

    // Hours come from the build (content/hours.json), so they live in
    // one place: {"0":[openMins, closeMins], …} with 0 = Sunday, plus
    // "special": {"2026-11-26": null | [openMins, closeMins]} for holiday
    // hours, which win over the weekly hours on their date (null = closed).
    var hours = {};
    try { hours = JSON.parse(($('meta[name="layers-hours"]') || {}).content || '{}'); } catch (e) {}
    var special = (hours && typeof hours.special === 'object' && hours.special) || {};
    function hoursOn(dow, ymd) {
      if (ymd && Object.prototype.hasOwnProperty.call(special, ymd)) return special[ymd];
      return hours[String(dow)] || null;
    }
    var today = hoursOn(now.dow, now.ymd);
    var next = hoursOn((now.dow + 1) % 7, now.ymd ? addDays(now.ymd, 1) : null);
    // today is a special day: mark its row instead of the weekday's
    var srow = now.ymd ? $('[data-special-hours] tr[data-date="' + now.ymd + '"]') : null;
    if (srow) srow.setAttribute('data-today', '');
    function label(m) {
      var h = Math.floor(m / 60), mm = m % 60, suf = h < 12 ? 'am' : 'pm';
      h = h % 12 || 12;
      return h + (mm ? ':' + (mm < 10 ? '0' : '') + mm : '') + suf;
    }
    var line;
    if (!today) {
      // closed all day (a holiday, or a weekly closed day)
      line = next ? 'Closed today · opens ' + label(next[0]) + ' tomorrow' : 'Closed today';
    } else if (now.mins >= today[0] && now.mins < today[1]) {
      line = 'Open now · until ' + label(today[1]);
    } else if (now.mins < today[0]) {
      line = 'Closed · opens ' + label(today[0]);
    } else {
      line = next ? 'Closed · opens ' + label(next[0]) + ' tomorrow' : 'Closed now';
    }

    els.forEach(function (el) {
      // The home visit band keeps its full hours line and appends the state;
      // the visit page element is dedicated to it.
      if (el.hasAttribute('data-open-now-only') || !el.textContent.trim()) {
        el.textContent = line;
      } else {
        el.textContent = line + '  ·  ' + el.textContent;
      }
    });

    if (table && !srow) {
      var row = $('tr[data-dow="' + now.dow + '"]', table);
      if (row) row.setAttribute('data-today', '');
    }
  }

  /* --------------------------------------------------------------------- */
  /* 7 · Catering form                                                      */
  /* --------------------------------------------------------------------- */
  function initCateringForm() {
    var form = $('#catering-form');
    if (!form) return;
    var status = $('[data-form-status]', form),
        submit = $('[data-submit]', form);

    function say(msg, tone) {
      if (!status) return;
      status.textContent = msg;
      if (tone) status.setAttribute('data-tone', tone);
      else status.removeAttribute('data-tone');
    }

    function markInvalid(field, on) {
      var wrap = field.closest('.field');
      if (!wrap) return;
      if (on) wrap.setAttribute('data-invalid', '');
      else wrap.removeAttribute('data-invalid');
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();

      var required = ['name', 'email', 'event_type'];
      var bad = null;
      required.forEach(function (n) {
        var f = form.elements[n];
        if (!f) return;
        var ok = f.value && f.value.trim() && (n !== 'email' || f.checkValidity());
        markInvalid(f, !ok);
        if (!ok && !bad) bad = f;
      });
      if (bad) { say('Please complete the highlighted fields.', 'err'); bad.focus(); return; }

      submit.setAttribute('data-busy', '');
      say('Sending…');

      fetch('/api/catering', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          name:        form.elements.name.value.trim(),
          email:       form.elements.email.value.trim(),
          event_type:  form.elements.event_type.value,
          event_date:  form.elements.event_date.value,
          guest_count: form.elements.guest_count.value,
          message:     form.elements.message.value.trim(),
          company:     form.elements.company.value   // honeypot
        })
      })
        .then(function (r) {
          return r.json().catch(function () { return {}; })
            .then(function (j) { return { ok: r.ok, body: j }; });
        })
        .then(function (res) {
          submit.removeAttribute('data-busy');
          if (res.ok) {
            form.reset();
            say('Thank you — your inquiry is on its way. We’ll reply within 1–2 business days.', 'ok');
          } else {
            say((res.body && res.body.error) ||
                'Something went wrong sending that. Please try again in a moment.', 'err');
          }
        })
        .catch(function () {
          submit.removeAttribute('data-busy');
          say('Network error — please try again, or reach us on Instagram.', 'err');
        });
    });

    $$('input,select,textarea', form).forEach(function (f) {
      f.addEventListener('input', function () { markInvalid(f, false); });
    });
  }


  /* --------------------------------------------------------------------- */
  /* 7b · Film band (home). Muted loop that plays only while on screen and  */
  /*      downloads nothing until it is about to be seen. Reduced motion or */
  /*      Save-Data: poster only, with the toggle offered to play it.       */
  /*      The toggle is the WCAG 2.2.2 pause control for moving content.    */
  /* --------------------------------------------------------------------- */
  function initFilm() {
    var film = $('[data-film]');
    if (!film) return;
    var video = $('video', film), toggle = $('[data-film-toggle]', film);
    if (!video) return;

    var saveData = !!(navigator.connection && navigator.connection.saveData);
    var userPaused = reduceMotion || saveData;   // the visitor's choice wins
    var inView = false;

    // Phones get the vertical cut. preload="none" means nothing has been fetched
    // yet, so swapping the source here costs nothing.
    var narrowSrc = film.getAttribute('data-src-narrow');
    if (narrowSrc && window.matchMedia && window.matchMedia('(max-width: 720px)').matches) {
      video.src = narrowSrc;
    }
    // The poster is a responsive <picture> under the video; the video fades in
    // over it once real frames are playing.
    video.addEventListener('playing', function () { film.setAttribute('data-playing', ''); });

    function reflect() {
      var paused = video.paused;
      if (paused) film.setAttribute('data-paused', '');
      else film.removeAttribute('data-paused');
      if (toggle) toggle.setAttribute('aria-label', paused ? 'Play the film' : 'Pause the film');
    }
    function play() {
      if (video.preload !== 'auto') video.preload = 'auto';
      var p = video.play();
      // Autoplay refused (e.g. iOS Low Power Mode): stay on the poster and stop
      // retrying on every scroll — the visitor can still press play.
      if (p && p.catch) p.catch(function () { userPaused = true; reflect(); });
    }
    function check() {
      var r = film.getBoundingClientRect();
      inView = r.bottom > -160 && r.top < (window.innerHeight || 800) + 160;
      if (inView && !userPaused && !document.hidden) { if (video.paused) play(); }
      else if (!video.paused) video.pause();
    }

    video.addEventListener('play', reflect);
    video.addEventListener('pause', reflect);
    reflect();

    if (toggle) {
      toggle.hidden = false;
      toggle.addEventListener('click', function () {
        if (video.paused) { userPaused = false; play(); }
        else { userPaused = true; video.pause(); }
      });
    }

    // Both an observer and a plain scroll check: observers ride rAF, which is
    // throttled to zero in background tabs (see the notes at the top).
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(check, { rootMargin: '160px 0px' }).observe(film);
    }
    var t = null;
    window.addEventListener('scroll', function () {
      if (t) return;
      t = window.setTimeout(function () { t = null; check(); }, 150);
    }, { passive: true });
    document.addEventListener('visibilitychange', check);
    window.addEventListener('pageshow', check);
    check();
  }


  /* --------------------------------------------------------------------- */
  /* 7c · Deep links. ScrollTrigger's load-time refresh restores the saved  */
  /*      scroll position and cancels the browser's jump to #hash, and the  */
  /*      live menu re-renders above it. Re-land until the visitor scrolls. */
  /* --------------------------------------------------------------------- */
  function initHashLanding() {
    var id = location.hash ? decodeURIComponent(location.hash.slice(1)) : '';
    var target = id && document.getElementById(id);
    if (!target) return;
    var moved = false;
    ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(function (t) {
      window.addEventListener(t, function () { moved = true; }, { passive: true, once: true });
    });
    function land() {
      if (moved) return;
      var el = document.getElementById(id);   // the menu may have replaced it
      if (el) el.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
    document.addEventListener('layers:menu-rendered', land);
    window.addEventListener('load', function () { window.setTimeout(land, 60); });
    if (window.ScrollTrigger && window.ScrollTrigger.addEventListener) {
      window.ScrollTrigger.addEventListener('refresh', land);
    }
    [400, 1200, 2600].forEach(function (ms) { window.setTimeout(land, ms); });
  }

  /* --------------------------------------------------------------------- */
  /* 8 · Motion — reveals per section, hero load-in, rescue sweep           */
  /* --------------------------------------------------------------------- */
  function initMotion() {
    if (reduceMotion || !window.gsap || !window.ScrollTrigger) return;

    var gsap = window.gsap, ST = window.ScrollTrigger;
    gsap.registerPlugin(ST);

    // Hero load-in — set+to, never from(): recoverable when rAF is dead.
    var heroItems = $$('[data-hero-item]');
    if (heroItems.length) {
      heroItems.forEach(function (el) { el.classList.add('dc-reveal-armed'); });
      gsap.set(heroItems, { opacity: 0, y: 26 });
      gsap.to(heroItems, {
        opacity: 1, y: 0, duration: .9, ease: 'power3.out', stagger: .14, delay: .15,
        onStart: function () {
          heroItems.forEach(function (el) { el.classList.remove('dc-reveal-armed'); });
        }
      });
    }

    var heroImg = $('#hero');
    if (heroImg) {
      gsap.to(heroImg, {
        // 10%, not more: .hero__media extends 12% above the hero (styles.css),
        // so this travel can never expose the ground behind the image.
        yPercent: 10, ease: 'none',
        scrollTrigger: { trigger: '#who', start: 'top top', end: 'bottom top', scrub: true }
      });
    }

    // Reveal the direct children of every content section below the hero —
    // but never menu cards (a shopper scanning fast must not chase fade-ins).
    $$('main > section:not(.hero):not([aria-label="Menu preview"])').forEach(function (sec) {
      if (sec.closest('.menu-wrap')) return;
      $$(':scope > .wrap, :scope > .comp-a__panel, :scope > .band__quote, :scope > .band__inner', sec)
        .forEach(function (el) {
          el.classList.add('dc-reveal-armed');
          gsap.set(el, { opacity: 0, y: 30 });
          ST.create({
            trigger: el, start: 'top 88%', once: true,
            onEnter: function () {
              el.classList.remove('dc-reveal-armed');
              gsap.to(el, { opacity: 1, y: 0, duration: .85, ease: 'power3.out' });
            }
          });
        });
    });

    // V3 editorial blocks opt in explicitly: only the few lines of copy move.
    // Photographs never fade in — an image-led page must not make people wait.
    $$('[data-reveal]').forEach(function (el) {
      if (el.classList.contains('dc-reveal-armed')) return;
      el.classList.add('dc-reveal-armed');
      gsap.set(el, { opacity: 0, y: 30 });
      ST.create({
        trigger: el, start: 'top 90%', once: true,
        onEnter: function () {
          el.classList.remove('dc-reveal-armed');
          gsap.to(el, { opacity: 1, y: 0, duration: .85, ease: 'power3.out' });
        }
      });
    });

    // Keyboard rescue: an armed (still transparent) element that takes focus is
    // revealed at once, so focus never lands on something invisible.
    document.addEventListener('focusin', function (e) {
      var el = e.target && e.target.closest ? e.target.closest('.dc-reveal-armed') : null;
      if (!el) return;
      el.classList.remove('dc-reveal-armed');
      gsap.set(el, { opacity: 1, y: 0 });
    });

    /* Rescue sweep: timers fire when rAF does not. Un-hides only what is in
       the viewport, so below-fold reveals keep their animation. */
    function rescueVisible() {
      var armed = $$('.dc-reveal-armed');
      armed.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) {
          el.classList.remove('dc-reveal-armed');
          gsap.set(el, { opacity: 1, y: 0 });
        }
      });
      return armed.length;
    }
    var sweep = window.setInterval(function () {
      if (rescueVisible() === 0) window.clearInterval(sweep);
    }, 1500);
    window.setTimeout(function () { rescueVisible(); ST.refresh(); }, 2600);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) { rescueVisible(); ST.refresh(); }
    });
    window.addEventListener('pageshow', function (e) {
      if (e.persisted) { rescueVisible(); ST.refresh(); }
    });
  }

  /* --------------------------------------------------------------------- */
  /* 9 · "Is my change live?" — whether the latest change has been          */
  /*     published, asked of GitHub (the repository is public, so no        */
  /*     sign-in): the newest run of a publishing workflow on the branch,   */
  /*     and — only when it failed — the open "Website update didn't        */
  /*     publish" issue the Actions bot keeps, for the link to what to fix. */
  /*     Runs on the /edit page (a card) and, in staff mode only, in the    */
  /*     editing bar (a short line). Visitors never get here: nothing       */
  /*     below runs, and nothing is fetched, unless one of those two asks.  */
  /*     The repository and branch are read back from the editor's address  */
  /*     (render.py REPO and BRANCH), so they can't drift from the Edit     */
  /*     buttons'. At most one request every 20 s, for 10 minutes while a   */
  /*     publish is running; a check that nothing changed (304) is free.    */
  /* --------------------------------------------------------------------- */
  var GITHUB_API = 'https://api.github.com/repos/';
  var PUBLISH_FLOWS = /\/(build-deploy|menu-refresh|undo|restore)\.yml(@.*)?$/;   // the workflows that publish
  var QUIET_RUN = /^(cancelled|skipped|neutral|stale)$/;     // a run that built nothing says nothing
  var PUBLISH_ISSUE = "website update didn't publish";
  var PUBLISH_BOT = 'github-actions[bot]';
  var STATUS_EVERY_MS = 20000;
  var STATUS_GIVE_UP_MS = 10 * 60 * 1000;

  function ago(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return '';
    var s = Math.max(0, Math.floor((Date.now() - t) / 1000));
    var m = Math.floor(s / 60), h = Math.floor(s / 3600), d = Math.floor(s / 86400);
    if (s < 60) return 'just now';
    if (m < 60) return (m === 1 ? 'a minute' : m + ' minutes') + ' ago';
    if (h < 24) return (h === 1 ? 'an hour' : h + ' hours') + ' ago';
    if (d === 1) return 'yesterday';
    if (d < 14) return d + ' days ago';
    try { return 'on ' + new Date(t).toLocaleDateString('en-US', { month: 'long', day: 'numeric' }); }
    catch (e) { return 'a while ago'; }
  }

  function repoOf(box) {
    var repo = box.getAttribute('data-repo') || '', branch = box.getAttribute('data-branch') || '';
    if (!repo) {       // the editing bar: the same names are in the editor's address
      var m = /^https:\/\/app\.pagescms\.org\/([\w.-]+\/[\w.-]+)\/([\w.-]+)/.exec(document.body.getAttribute('data-edit-root') || '');
      if (m) { repo = m[1]; branch = m[2]; }
    }
    return /^[\w.-]+\/[\w.-]+$/.test(repo) && /^[\w.-]+$/.test(branch) ? { repo: repo, branch: branch } : null;
  }

  function getJSON(url) {
    return window.fetch(url, { cache: 'no-cache', headers: { accept: 'application/vnd.github+json' } })
      .then(function (r) { if (!r.ok) throw new Error('GitHub said ' + r.status); return r.json(); });
  }

  // The words for each state: the card on /edit, or the short line in the bar.
  function statusWords(compact, state, when) {
    if (state === 'ok') return compact ? '✓ Website up to date · ' + when : '✓ Your website is up to date — last updated ' + when;
    if (state === 'publishing') return compact ? '⏳ Publishing your change…' : '⏳ Publishing your latest change… this usually takes about 2 minutes';
    if (state === 'slow') return compact ? '⏳ Still publishing…' : '⏳ Still publishing. Reload this page in a few minutes to check again.';
    if (state === 'problem') return '⚠ Your last change didn’t go live. ';
    return compact ? 'Can’t check right now' : 'Couldn’t check right now — try again in a minute.';
  }

  function publishStatus(box, compact) {
    var where = repoOf(box);
    var text = $('.edit-status__text', box) || box;
    var started = Date.now(), checked = 0, timer = null;

    // Says it only when it changed, so a screen reader isn't told the same
    // thing every 20 seconds.
    function say(state, when, link) {
      var words = statusWords(compact, state, when) + (link || '');
      if (text.getAttribute('data-said') === words) return;
      text.setAttribute('data-said', words);
      box.setAttribute('data-state', state);
      text.textContent = statusWords(compact, state, when);
      if (state === 'problem' && link) {
        var a = document.createElement('a');
        a.href = link;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = compact ? 'See why →' : 'See what to fix →';
        var hint = document.createElement('span');
        hint.className = 'sr-only';
        hint.textContent = ' (opens in a new tab)';
        a.appendChild(hint);
        text.appendChild(a);
      }
    }

    function again(state) {
      if (Date.now() - started > STATUS_GIVE_UP_MS) return say('slow');
      say(state);
      timer = window.setTimeout(check, STATUS_EVERY_MS);
    }

    function check() {
      window.clearTimeout(timer);
      checked = Date.now();
      if (!where || !window.fetch) return say('error');
      getJSON(GITHUB_API + where.repo + '/actions/runs?branch=' + encodeURIComponent(where.branch) + '&per_page=10')
        .then(function (data) {
          var run = (data.workflow_runs || []).filter(function (r) {
            return PUBLISH_FLOWS.test(r.path || '') && !(r.status === 'completed' && QUIET_RUN.test(r.conclusion || ''));
          })[0];
          if (!run) return say('error');
          if (run.status !== 'completed') return again('publishing');
          if (run.conclusion === 'success') return say('ok', ago(run.updated_at || run.run_started_at));
          // it didn't go live: the issue the Actions bot opened says what to fix
          return getJSON(GITHUB_API + where.repo + '/issues?state=open&per_page=10').then(function (issues) {
            var issue = (issues || []).filter(function (i) {
              return !i.pull_request && i.user && i.user.login === PUBLISH_BOT &&
                String(i.title || '').replace(/’/g, "'").trim().toLowerCase() === PUBLISH_ISSUE;
            })[0];
            say('problem', '', (issue || run).html_url);
          });
        })
        .catch(function () { say('error'); });
    }

    check();
    // back from saving in the editor's tab: look again, so the change just made shows up
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && Date.now() - checked > 15000) { started = Date.now(); check(); }
    });
  }

  // The card on /edit: asked for by the page itself.
  function initPublishStatus() {
    var card = $('[data-publish-status]');
    if (card) publishStatus(card, false);
  }

  /* --------------------------------------------------------------------- */
  /* 10 · Staff mode: Edit buttons on the website itself. Turned on by ?edit */
  /*     (the /edit page's "Show Edit buttons on the website") and off by   */
  /*     ?edit=off, remembered in this browser. When on, every region the   */
  /*     build marked with data-edit (tools/render.py edit_attr) gets a     */
  /*     small "✎ Edit" link to that part of the editor, and a slim bar     */
  /*     offers "Edit this page", "Open the editor" and "Hide edit          */
  /*     buttons". When off — every visitor — nothing happens at all: no    */
  /*     element is added, nothing is fetched, the layout is untouched.     */
  /*     Runs last, after the open-now lines have their text (it replaces   */
  /*     their contents) and after the motion has picked its targets.       */
  /* --------------------------------------------------------------------- */
  var EDIT_KEY = 'layers-edit';

  function setEditFlag(on) {
    try {
      if (on) window.localStorage.setItem(EDIT_KEY, '1');
      else window.localStorage.removeItem(EDIT_KEY);
      return true;
    } catch (e) { return false; }
  }

  function staffModeWanted() {
    var q = null, asked = null;
    try {
      q = new URLSearchParams(window.location.search);
      if (q.has('edit')) asked = !/^(off|0|false|no|hide)$/i.test(q.get('edit') || '');
    } catch (e) {}
    if (asked === null) {
      try { return window.localStorage.getItem(EDIT_KEY) === '1'; } catch (e) { return false; }
    }
    // Remembered: take ?edit out of the address bar, so a link copied from
    // here doesn't carry it. (Not remembered — storage blocked — it stays,
    // and staff mode lasts for this page only.)
    if (setEditFlag(asked)) {
      try {
        q.delete('edit');
        var rest = q.toString();
        window.history.replaceState(window.history.state, '',
          window.location.pathname + (rest ? '?' + rest : '') + window.location.hash);
      } catch (e) {}
    }
    return asked;
  }

  var EDIT_HOLDERS = /^(A|BUTTON|SUMMARY|LABEL|SELECT|TEXTAREA|INPUT|TABLE|DETAILS)$/;

  function addEditChip(host) {
    var url = host.getAttribute('data-edit') || '';
    if (!/^https:\/\//.test(url)) return;
    // A link can't sit inside a button or a link (the album tiles: their
    // Edit link is in the album viewer instead); in a list it goes in the
    // first item.
    if (EDIT_HOLDERS.test(host.tagName)) return;
    var box = /^(OL|UL)$/.test(host.tagName) ? host.querySelector('li') : host;
    if (!box) return;
    var label = host.getAttribute('data-edit-label') || 'Edit this part of the page';
    var what = label.replace(/^Edit\s*/i, '');
    var a = document.createElement('a');
    a.className = 'edit-chip';
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener';
    // one span for the words: in a flex box, spaces between separate items vanish
    a.innerHTML = '<span class="edit-chip__icon" aria-hidden="true">✎</span><span class="edit-chip__text">' +
      '<span class="edit-chip__word">Edit</span><span class="edit-chip__what"></span></span>' +
      '<span class="sr-only"> (opens the editor in a new tab)</span>';
    $('.edit-chip__what', a).textContent = what ? ' ' + what : '';
    // the chip is placed over the region's corner (position:absolute): the
    // region becomes its frame, which changes nothing about how it's laid out
    if (window.getComputedStyle(box).position === 'static') box.classList.add('edit-host');
    box.insertBefore(a, box.firstChild);      // first in the region, so Tab reaches it first
  }

  function addViewerEdit() {
    var viewer = $('#album-viewer');
    var top = viewer && $('.viewer__top', viewer);
    if (!top) return;
    var a = document.createElement('a');
    a.className = 'viewer__edit';
    a.target = '_blank';
    a.rel = 'noopener';
    a.hidden = true;
    a.innerHTML = '<span aria-hidden="true">✎</span> Edit this album<span class="sr-only"> (opens the editor in a new tab)</span>';
    top.insertBefore(a, $('[data-viewer-close]', top));
    $$('[data-album][data-edit]').forEach(function (tile) {
      tile.addEventListener('click', function () {
        a.href = tile.getAttribute('data-edit');
        a.hidden = !/^https:\/\//.test(a.href);
      });
    });
  }

  function staffModeOff() {
    setEditFlag(false);
    $$('.edit-chip, .edit-bar, .viewer__edit').forEach(function (el) { el.parentNode.removeChild(el); });
    $$('.edit-host').forEach(function (el) { el.classList.remove('edit-host'); });
    document.documentElement.classList.remove('is-editing');
    var note = document.createElement('p');
    note.className = 'edit-toast';
    note.setAttribute('role', 'status');
    document.body.appendChild(note);
    // filled in a moment later, so screen readers announce it
    window.setTimeout(function () { note.textContent = 'Edit buttons hidden. To show them again, open the /edit page.'; }, 60);
    window.setTimeout(function () { if (note.parentNode) note.parentNode.removeChild(note); }, 6000);
    var main = $('#main');
    if (main) { main.setAttribute('tabindex', '-1'); main.focus({ preventScroll: true }); }
  }

  function addEditBar() {
    var body = document.body;
    var root = body.getAttribute('data-edit-root') || '';
    var page = body.getAttribute('data-edit-page') || '';
    if (!/^https:\/\//.test(root)) return;
    var bar = document.createElement('div');
    bar.className = 'edit-bar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Editing tools');
    bar.innerHTML = '<p class="edit-bar__label"><span aria-hidden="true">✎</span> Editing tools</p>' +
      '<p class="edit-bar__status" role="status" aria-live="polite" data-bar-status><span class="edit-status__text"></span></p>' +
      (/^https:\/\//.test(page) ? '<a class="edit-bar__btn edit-bar__btn--main" target="_blank" rel="noopener" data-bar-page>' +
        '<span>Edit this page</span><span class="sr-only"> (opens the editor in a new tab)</span></a>' : '') +
      // on a phone the words in .edit-bar__long are left out: "Open editor", "Hide buttons"
      '<a class="edit-bar__btn" target="_blank" rel="noopener" data-bar-root><span>Open<span class="edit-bar__long"> the</span>' +
        ' editor</span><span class="sr-only"> (opens in a new tab)</span></a>' +
      '<button class="edit-bar__btn" type="button" data-bar-hide><span>Hide<span class="edit-bar__long"> edit</span> buttons</span></button>';
    var p = $('[data-bar-page]', bar);
    if (p) p.href = page;
    $('[data-bar-root]', bar).href = root;
    $('[data-bar-hide]', bar).addEventListener('click', staffModeOff);
    // Early in the page, right after "Skip to content": the bar is fixed at
    // the bottom of the screen, but a keyboard reaches it in DOM order, and
    // it shouldn't take a Tab through the whole page and footer first.
    var skip = $('.skip-link');
    body.insertBefore(bar, skip ? skip.nextSibling : body.firstChild);
    publishStatus($('[data-bar-status]', bar), true);       // staff mode only: addEditBar runs after "if (!on) return;"
  }

  function initStaffMode() {
    var on = staffModeWanted();
    var state = $('[data-edit-state]');          // the /edit page says which it is
    if (state) {
      state.textContent = on ? 'Edit buttons are on in this browser. Open any page of the website to see them.'
                             : 'Edit buttons are off in this browser.';
    }
    if (!on) return;
    document.documentElement.classList.add('is-editing');
    $$('[data-edit]').forEach(addEditChip);
    addViewerEdit();
    if (!document.body.classList.contains('page-edit')) addEditBar();
  }

  /* --------------------------------------------------------------------- */
  function boot() {
    var y = $('[data-year]');
    if (y) y.textContent = String(new Date().getFullYear());

    initAnnouncement();
    initDated();
    initHeader();
    initDrawer();
    initSheet();
    initMenu();
    initOpenNow();
    initOrderFrame();
    initAlbums();
    initFilm();
    initCateringForm();
    initMotion();
    initHashLanding();
    initStaffMode();
    initPublishStatus();
  }

  if (document.readyState !== 'loading') boot();
  else document.addEventListener('DOMContentLoaded', boot);
})();
