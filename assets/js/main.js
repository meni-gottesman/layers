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

  var SQUARE_ORDER = 'https://layers.square.site';
  var PLACEHOLDER_FACE = '/layers/assets/img/face.png';

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
      var mq = window.matchMedia('(min-width:1001px)');
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
    var nameEl = $('[data-sheet-name]', sheet);
    nameEl.textContent = item.name || '';
    if (item.note) {
      var note = document.createElement('span');
      note.className = 'menu-card__note';
      note.textContent = ' (' + item.note + ')';
      nameEl.appendChild(note);
    }
    var priceEl = $('[data-sheet-price]', sheet);
    priceEl.textContent = item.price ? money(item.price) : '';
    var calEl = $('[data-sheet-cal]', sheet);
    calEl.textContent = item.calories ? item.calories + ' CAL' : (item.soldOut ? 'Sold out' : '');
    var order = $('[data-sheet-order]', sheet);
    order.setAttribute('aria-label', 'Order ' + (item.name || 'item') + ' on Square');
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
  /* 4 · Category chip rail: build from rendered sections + scroll-spy      */
  /* --------------------------------------------------------------------- */
  function rebuildChips() {
    var track = $('[data-chip-track]');
    if (!track) return;
    var sections = $$('[data-cat-section]');
    track.innerHTML = '';
    sections.forEach(function (sec) {
      var name = $('.cathead__name', sec) || $('.cathead .eyebrow', sec);
      var a = document.createElement('a');
      a.className = 'chip';
      a.href = '#' + sec.id;
      a.setAttribute('data-chip', sec.id);
      a.textContent = name ? name.textContent : sec.id;
      track.appendChild(a);
    });
    spyChips();
  }

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

  var ARROW = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/></svg>';

  function buildCard(item) {
    var card = document.createElement('article');
    card.className = 'menu-card';
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
    if (src) {
      var img = document.createElement('img');
      img.src = src; img.alt = ''; img.loading = 'lazy'; img.decoding = 'async';
      img.width = 800; img.height = 800;
      img.addEventListener('error', function handle() {
        img.removeEventListener('error', handle);
        media.innerHTML = '';
        media.className = 'menu-card__media menu-card__media--ph';
        media.innerHTML = '<img src="' + PLACEHOLDER_FACE + '" alt="" width="88" height="88">';
      });
      media.appendChild(img);
    } else {
      // No photo: branded placeholder at the same 1:1 ratio — grid never reflows.
      media.className = 'menu-card__media menu-card__media--ph';
      media.innerHTML = '<img src="' + PLACEHOLDER_FACE + '" alt="" width="88" height="88">';
    }

    var body = document.createElement('span');
    body.className = 'menu-card__body';

    var kind = document.createElement('span');
    kind.className = 'menu-card__kind';
    kind.textContent = item.kind || '';

    var name = document.createElement('span');
    name.className = 'menu-card__name';
    name.textContent = item.name || '';
    if (item.note) {
      var note = document.createElement('span');
      note.className = 'menu-card__note';
      note.textContent = ' (' + item.note + ')';
      name.appendChild(note);
    }

    var meta = document.createElement('span');
    meta.className = 'menu-card__meta';
    if (item.price != null && item.price !== '') {
      var price = document.createElement('span');
      price.className = 'menu-card__price';
      price.textContent = money(item.price);
      meta.appendChild(price);
    }
    if (item.calories) {
      var cal = document.createElement('span');
      cal.className = 'menu-card__cal';
      cal.textContent = item.calories + ' CAL';
      meta.appendChild(cal);
    }
    if (item.soldOut) {
      var so = document.createElement('span');
      so.className = 'menu-card__sold';
      so.textContent = 'Sold out';
      meta.appendChild(so);
    }

    body.appendChild(kind); body.appendChild(name); body.appendChild(meta);
    open.appendChild(media); open.appendChild(body);
    card.appendChild(open);

    // Sold out: the ordering control is removed entirely, not disabled.
    if (!item.soldOut) {
      var order = document.createElement('a');
      order.className = 'menu-card__order';
      order.href = SQUARE_ORDER;
      order.target = '_blank'; order.rel = 'noopener';
      order.setAttribute('aria-label', 'Order ' + (item.name || 'item') + ' on Square');
      order.innerHTML = 'Order on Square' + ARROW;
      card.appendChild(order);
    }
    return card;
  }

  function initMenu() {
    var root = $('[data-menu-page]');
    if (!root) return;
    var statusEl = $('[data-menu-status]'), dot = $('[data-menu-dot]');

    function markCached() {
      if (dot) dot.setAttribute('data-state', 'stale');
      if (statusEl) {
        statusEl.textContent =
          'Showing our current menu. Live pricing and availability are on Square.';
      }
    }

    fetch('/api/menu', { headers: { accept: 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('menu ' + r.status); return r.json(); })
      .then(function (data) {
        if (!data || !Array.isArray(data.categories) || !data.categories.length) return;
        if (data.source === 'fallback') { markCached(); return; }

        var frag = document.createDocumentFragment();
        var first = true;
        data.categories.forEach(function (cat) {
          if (!cat.items || !cat.items.length) return;   // empty never renders
          var sec = document.createElement('section');
          sec.className = 'menu-group';
          sec.id = slugify(cat.name);
          sec.setAttribute('data-cat-section', '');

          var head = document.createElement('header');
          if (first) {
            head.className = 'cathead cathead--field';
            head.innerHTML = '<p class="eyebrow eyebrow--onsage">Made in house</p>' +
              '<h2 class="cathead__name"></h2>';
            $('.cathead__name', head).textContent = cat.name || 'Menu';
            first = false;
          } else {
            head.className = 'cathead';
            var ey = document.createElement('p');
            ey.className = 'eyebrow';
            ey.textContent = cat.name || 'Menu';
            head.appendChild(ey);
          }
          sec.appendChild(head);

          var grid = document.createElement('div');
          grid.className = 'menu-grid';
          cat.items.forEach(function (it) { grid.appendChild(buildCard(it)); });
          sec.appendChild(grid);
          frag.appendChild(sec);
        });
        if (!frag.childNodes.length) return;

        root.innerHTML = '';
        root.appendChild(frag);
        rebuildChips();
        if (window.gsap && window.ScrollTrigger) window.ScrollTrigger.refresh();
      })
      .catch(markCached);   // Square unreachable — pre-rendered menu stays put

    spyChips();
  }

  /* --------------------------------------------------------------------- */
  /* 6 · Open-now line + hours table                                        */
  /*     Hours: Mon–Fri 10–17, Sat–Sun 10–16, America/Los_Angeles.          */
  /* --------------------------------------------------------------------- */
  function shopClock() {
    try {
      var parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/Los_Angeles',
        weekday: 'short', hour: 'numeric', hour12: false, minute: 'numeric'
      }).formatToParts(new Date());
      var get = function (t) {
        var p = parts.filter(function (x) { return x.type === t; })[0];
        return p ? p.value : null;
      };
      var dowMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
      return {
        dow: dowMap[get('weekday')],
        mins: parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10)
      };
    } catch (e) { return null; }
  }

  function initOpenNow() {
    var els = $$('[data-open-now]');
    var table = $('[data-hours]');
    if (!els.length && !table) return;

    var now = shopClock();
    if (!now) return;

    var weekend = now.dow === 0 || now.dow === 6;
    var closeMins = weekend ? 16 * 60 : 17 * 60;
    var openMins = 10 * 60;
    var isOpen = now.mins >= openMins && now.mins < closeMins;
    var line = isOpen ? 'Open now' : 'Closed · opens 10am';

    els.forEach(function (el) {
      // The home visit band keeps its full hours line and appends the state;
      // the visit page element is dedicated to it.
      if (el.hasAttribute('data-open-now-only') || !el.textContent.trim()) {
        el.textContent = line;
      } else {
        el.textContent = line + '  ·  ' + el.textContent;
      }
    });

    if (table) {
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
      gsap.set(heroItems, { autoAlpha: 0, y: 26 });
      gsap.to(heroItems, {
        autoAlpha: 1, y: 0, duration: .9, ease: 'power3.out', stagger: .14, delay: .15,
        onStart: function () {
          heroItems.forEach(function (el) { el.classList.remove('dc-reveal-armed'); });
        }
      });
    }

    var heroImg = $('#hero');
    if (heroImg) {
      gsap.to(heroImg, {
        yPercent: 12, ease: 'none',
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
          gsap.set(el, { autoAlpha: 0, y: 30 });
          ST.create({
            trigger: el, start: 'top 88%', once: true,
            onEnter: function () {
              el.classList.remove('dc-reveal-armed');
              gsap.to(el, { autoAlpha: 1, y: 0, duration: .85, ease: 'power3.out' });
            }
          });
        });
    });

    /* Rescue sweep: timers fire when rAF does not. Un-hides only what is in
       the viewport, so below-fold reveals keep their animation. */
    function rescueVisible() {
      var armed = $$('.dc-reveal-armed');
      armed.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) {
          el.classList.remove('dc-reveal-armed');
          gsap.set(el, { autoAlpha: 1, y: 0 });
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
  function boot() {
    var y = $('[data-year]');
    if (y) y.textContent = String(new Date().getFullYear());

    initHeader();
    initDrawer();
    initSheet();
    initMenu();
    initOpenNow();
    initCateringForm();
    initMotion();
  }

  if (document.readyState !== 'loading') boot();
  else document.addEventListener('DOMContentLoaded', boot);
})();
