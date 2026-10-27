/* ==========================================================================
   Layers — staff tools (/photo-prep and /brand only).
   main.js runs on every page; this file is loaded by the two staff pages
   alone, so visitors never download it. Nothing here talks to a server: a
   photo is read, resized and re-encoded inside the browser.
   ========================================================================== */
(function () {
  'use strict';

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* --------------------------------------------------------------------- */
  /* Prepare a photo (/photo-prep). The hosted Pages CMS rejects uploads    */
  /* over about 3.3 MB (CMS_SPEC §8.8); phone photos are often bigger. The  */
  /* copy made here is a JPEG of at most MAX_EDGE px on its long side and   */
  /* under LIMIT bytes. Re-encoding through a canvas also leaves out the    */
  /* camera's hidden details (location, device), which matters because     */
  /* uploads are stored in a public repository.                             */
  /* --------------------------------------------------------------------- */
  var MAX_EDGE = 2400;                              // px, long edge
  var LIMIT = 3000000;                              // bytes: "under 3 MB", with room below the CMS's limit
  var QUALITIES = [0.85, 0.8, 0.75, 0.7, 0.65, 0.6];
  var MAX_STEP_AREA = 4096 * 4096;                  // the largest canvas older iPhones allow

  function px(w, h) { return w.toLocaleString('en-US') + ' × ' + h.toLocaleString('en-US') + ' px'; }

  function bytes(n) {
    return n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1e3)) + ' KB';
  }

  function kind(file) {
    var ext = (/\.([a-z0-9]{2,5})$/i.exec(file.name || '') || [])[1];
    if (ext) return ext.toUpperCase().replace('JPEG', 'JPG');
    return ((file.type || '').split('/')[1] || 'photo').toUpperCase();
  }

  function isHeic(file) { return /hei[cf]/i.test(file.type || '') || /\.hei[cf]$/i.test(file.name || ''); }

  /* "IMG_1234.HEIC" -> "IMG_1234-web.jpg": letters, digits, dots, dashes only,
     so the CMS keeps the name as it is. */
  function downloadName(file) {
    var base = (file.name || '').replace(/\.[^.]*$/, '').replace(/[^\w.-]+/g, '-')
      .replace(/-{2,}/g, '-').replace(/^[-.]+|[-.]+$/g, '');
    return (base || 'photo') + '-web.jpg';
  }

  /* Decode with the photo's own orientation: phones save many photos sideways
     with a "rotate me" tag. createImageBitmap(…, {imageOrientation:
     'from-image'}) applies it; a browser that doesn't know the option (or
     can't decode the file that way) falls back to an <img>, which applies the
     tag too. Rejects with "decode" when the browser can't read the file at
     all (HEIC in Chrome, for example). */
  function decode(file) {
    function viaImg() {
      return new Promise(function (resolve, reject) {
        var url = URL.createObjectURL(file), img = new Image();
        img.onload = function () {
          resolve({ src: img, w: img.naturalWidth, h: img.naturalHeight,
                    done: function () { URL.revokeObjectURL(url); } });
        };
        img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
        img.src = url;
      });
    }
    if (!window.createImageBitmap) return viaImg();
    var p;
    try { p = window.createImageBitmap(file, { imageOrientation: 'from-image' }); } catch (e) { return viaImg(); }
    return p.then(function (bmp) {
      return { src: bmp, w: bmp.width, h: bmp.height, done: function () { if (bmp.close) bmp.close(); } };
    }, viaImg);
  }

  function makeCanvas(w, h) {
    var c = document.createElement('canvas');
    c.width = w; c.height = h;
    return c;
  }

  /* Draw the photo at w × h. A photo more than twice the target is halved in
     steps first: one big jump makes browsers skip pixels (jagged edges,
     shimmering fine detail). */
  function draw(src, sw, sh, w, h) {
    var cur = src, cw = sw, ch = sh, ctx;
    while (cw / 2 >= w && (cw / 2) * (ch / 2) <= MAX_STEP_AREA) {
      var nw = Math.round(cw / 2), nh = Math.round(ch / 2), step = makeCanvas(nw, nh);
      ctx = step.getContext('2d');
      ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(cur, 0, 0, nw, nh);
      if (cur !== src) { cur.width = 0; cur.height = 0; }        // free the previous step's memory
      cur = step; cw = nw; ch = nh;
    }
    var out = makeCanvas(w, h);
    ctx = out.getContext('2d');
    ctx.fillStyle = '#ffffff';                                   // a see-through PNG gets white, not black
    ctx.fillRect(0, 0, w, h);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(cur, 0, 0, w, h);
    if (cur !== src) { cur.width = 0; cur.height = 0; }
    return out;
  }

  function toJpeg(canvas, quality) {
    return new Promise(function (resolve) { canvas.toBlob(resolve, 'image/jpeg', quality); });
  }

  /* JPEG at quality 0.85, stepping the quality down until it's under LIMIT;
     if even the lowest quality is too big (rare at 2400 px), a little smaller. */
  function encode(src, sw, sh) {
    var tries = 0;
    function atScale(s) {
      var w = Math.max(1, Math.round(sw * s)), h = Math.max(1, Math.round(sh * s));
      var canvas = draw(src, sw, sh, w, h), i = 0;
      function next() {
        return toJpeg(canvas, QUALITIES[i]).then(function (blob) {
          if (!blob) throw new Error('encode');
          if (blob.size < LIMIT) { canvas.width = 0; canvas.height = 0; return { blob: blob, w: w, h: h }; }
          if (++i < QUALITIES.length) return next();
          canvas.width = 0; canvas.height = 0;
          if (++tries > 6) throw new Error('encode');
          return atScale(s * 0.85);
        });
      }
      return next();
    }
    return atScale(Math.min(1, MAX_EDGE / Math.max(sw, sh)));
  }

  function initPhotoPrep() {
    var root = $('[data-photo-prep]');
    if (!root || !window.Promise || !window.URL) return;
    var input = $('[data-pp-input]', root), drop = $('[data-pp-drop]', root);
    var status = $('[data-pp-status]', root), help = $('[data-pp-help]', root);
    var result = $('[data-pp-result]', root), preview = $('[data-pp-preview]', root);
    var before = $('[data-pp-before]', root), after = $('[data-pp-after]', root);
    var note = $('[data-pp-note]', root), link = $('[data-pp-download]', root);
    var urls = [], token = 0;

    function say(msg) { status.textContent = msg; }

    function reset() {
      urls.forEach(function (u) { URL.revokeObjectURL(u); });
      urls = [];
      result.hidden = true; help.hidden = true; note.hidden = true;
    }

    function show(file, w, h, out) {
      var url = URL.createObjectURL(out.blob);
      urls.push(url);
      preview.src = url;
      preview.width = out.w; preview.height = out.h;
      before.textContent = px(w, h) + ' · ' + bytes(file.size) + ' · ' + kind(file);
      after.textContent = px(out.w, out.h) + ' · ' + bytes(out.blob.size) + ' · JPG';
      link.href = url;
      link.setAttribute('download', downloadName(file));
      // The editor accepts any size; it's the WEBSITE that refuses a photo too
      // small for its spot, after cropping it to the spot's shape — so the
      // update doesn't publish. Say that plainly, as a warning.
      var long = Math.max(out.w, out.h), lead = '', msg = '';
      if (long < 800) {
        lead = 'Too small for the website. ';
        msg = 'This photo is ' + long + ' pixels on its long side. Photo spots need at least 800 pixels ' +
              '(1,200 for the wide photos across the page) after the photo is cropped to the spot’s shape, so ' +
              'the website won’t publish it in most spots. Use the original photo from the phone or camera instead.';
      } else if (long < 1200) {
        lead = 'Not for the wide photos. ';
        msg = 'Big enough for the smaller spots, but the wide photos across the page need at least 1,200 pixels. ' +
              'Each spot crops the photo to its shape, so a photo near the limit can still be too small for a ' +
              'spot of a different shape — the original from the phone or camera is safest.';
      } else if (Math.max(w, h) <= MAX_EDGE && file.size < LIMIT && /jpe?g/i.test(file.type || '')) {
        msg = 'Your photo was already small enough to upload. This copy is the same size, without the hidden details.';
      }
      note.textContent = '';
      if (lead) {
        var strong = document.createElement('strong');
        strong.textContent = lead;
        note.appendChild(strong);
        note.setAttribute('data-tone', 'warn');
      } else {
        note.removeAttribute('data-tone');
      }
      note.appendChild(document.createTextNode(msg));
      note.hidden = !msg;
      result.hidden = false;
      say('Done. The prepared copy is ' + px(out.w, out.h) + ' and ' + bytes(out.blob.size) +
          '. The download button is below the preview.');
    }

    function handle(file) {
      if (!file) return;
      var mine = ++token;                      // a newer photo wins over one still being prepared
      reset();
      if (file.type && !/^image\//.test(file.type) && !isHeic(file)) {
        say('That file isn’t a photo. Choose a JPEG, PNG, WebP or iPhone (HEIC) photo.');
        return;
      }
      root.setAttribute('aria-busy', 'true');
      say('Preparing your photo…');
      decode(file).then(function (img) {
        if (mine !== token) { img.done(); return; }
        return encode(img.src, img.w, img.h).then(function (out) {
          img.done();
          if (mine === token) show(file, img.w, img.h, out);
        }, function (e) { img.done(); throw e; });
      }).catch(function (e) {
        if (mine !== token) return;
        if (e && e.message === 'decode') {
          say('That photo didn’t open. There are two easy fixes below.');
          help.hidden = false;
          help.focus();
        } else {
          say('Something went wrong while preparing that photo. Try again, or open this page in another browser.');
        }
      }).then(function () {
        if (mine === token) root.removeAttribute('aria-busy');
      });
    }

    input.addEventListener('change', function () {
      var f = input.files && input.files[0];
      input.value = '';                        // choosing the same photo again still works
      handle(f);
    });

    // Drag and drop: a photo dropped anywhere on the page is used (and the
    // browser doesn't leave the page to show it); the box lights up meanwhile.
    function hasFiles(e) {
      var t = e.dataTransfer && e.dataTransfer.types;
      return !!t && Array.prototype.indexOf.call(t, 'Files') !== -1;
    }
    document.addEventListener('dragover', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      drop.classList.add('is-over');
    });
    document.addEventListener('dragleave', function (e) {
      if (!e.relatedTarget) drop.classList.remove('is-over');   // left the window
    });
    document.addEventListener('drop', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      drop.classList.remove('is-over');
      handle(e.dataTransfer.files[0]);
    });
  }

  /* --------------------------------------------------------------------- */
  /* Brand kit (/brand): "Copy" next to each colour's hex value. The        */
  /* buttons stay hidden where the browser can't copy.                      */
  /* --------------------------------------------------------------------- */
  function initCopy() {
    var buttons = $$('[data-copy]');
    if (!buttons.length || !navigator.clipboard || !window.isSecureContext) return;
    var status = $('[data-copy-status]');
    buttons.forEach(function (b) {
      b.hidden = false;
      var label = b.firstChild, timer;
      b.addEventListener('click', function () {
        var value = b.getAttribute('data-copy');
        navigator.clipboard.writeText(value).then(function () {
          label.nodeValue = 'Copied';
          if (status) status.textContent = 'Copied ' + value;
          window.clearTimeout(timer);
          timer = window.setTimeout(function () { label.nodeValue = 'Copy'; }, 1600);
        }, function () {
          if (status) status.textContent = 'Couldn’t copy. Select the code and copy it by hand.';
        });
      });
    });
  }

  function boot() {
    initPhotoPrep();
    initCopy();
  }

  if (document.readyState !== 'loading') boot();
  else document.addEventListener('DOMContentLoaded', boot);
})();
