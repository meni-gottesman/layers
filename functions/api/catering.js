/**
 * POST /api/catering — catering inquiry handler.
 *
 * Contract requirement (§01 / client email 2026-06-28):
 *   "We don't want the destination email shown as plain text anywhere on the
 *    page." CATERING_TO is a secret binding. It is never rendered into HTML,
 *    never echoed in a response body, and never included in an error message.
 *
 * Spam protection is layered:
 *   1. Honeypot  — the `company` field is invisible to humans. Filled => drop.
 *   2. Turnstile — server-side CAPTCHA verification, active once keys exist.
 *   3. Rate limit — per-IP, via the optional RATE_LIMIT KV namespace.
 *   4. Field caps — hard length limits before anything is composed.
 *
 * Required bindings:
 *   CATERING_TO        destination inbox            (secret)
 *   CATERING_FROM      verified sender address      (secret or var)
 *   RESEND_API_KEY     transactional email key      (secret)
 * Optional bindings:
 *   TURNSTILE_SECRET   enables CAPTCHA when present (secret)
 *   RATE_LIMIT         KV namespace for throttling
 */

const LIMITS = { name: 120, email: 200, event_type: 60, message: 4000 };
const RATE = { max: 5, windowSeconds: 3600 };

const EVENT_TYPES = new Set([
  'Team breakfast', 'Wellness event', 'Corporate meeting', 'Private celebration', 'Other',
]);

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}

/** Escape before interpolating anything user-supplied into the HTML email. */
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Strip CR/LF so nothing user-supplied can forge an email header. */
function oneLine(s, max) {
  return String(s ?? '').replace(/[\r\n]+/g, ' ').trim().slice(0, max);
}

function validEmail(s) {
  return typeof s === 'string' && s.length <= LIMITS.email && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s);
}

async function verifyTurnstile(secret, token, ip) {
  if (!secret) return true;                 // not configured yet — skip, don't block
  if (!token) return false;
  try {
    const body = new FormData();
    body.append('secret', secret);
    body.append('response', token);
    if (ip) body.append('remoteip', ip);
    const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST', body, signal: AbortSignal.timeout(5000),
    });
    const out = await res.json();
    return out.success === true;
  } catch {
    return false;
  }
}

async function underRateLimit(kv, ip) {
  if (!kv || !ip) return true;
  try {
    const key = `catering:${ip}`;
    const current = parseInt((await kv.get(key)) || '0', 10);
    if (current >= RATE.max) return false;
    await kv.put(key, String(current + 1), { expirationTtl: RATE.windowSeconds });
    return true;
  } catch {
    return true;    // never let the limiter itself take the form down
  }
}

async function readBody(request) {
  const ct = request.headers.get('content-type') || '';
  if (ct.includes('application/json')) return await request.json();
  if (ct.includes('form')) {
    const fd = await request.formData();
    return Object.fromEntries(fd.entries());
  }
  return {};
}

export async function onRequestPost(context) {
  const { request, env } = context;
  const ip = request.headers.get('cf-connecting-ip') || '';

  let data;
  try {
    data = await readBody(request);
  } catch {
    return json({ error: 'Could not read that submission.' }, 400);
  }

  // --- 1 · Honeypot -------------------------------------------------------
  // Silent 200: a bot that sees an error learns to try again.
  if (typeof data.company === 'string' && data.company.trim() !== '') {
    return json({ ok: true });
  }

  // --- 2 · CAPTCHA --------------------------------------------------------
  const captchaOk = await verifyTurnstile(
    env.TURNSTILE_SECRET,
    data['cf-turnstile-response'] || data.turnstile_token,
    ip
  );
  if (!captchaOk) {
    return json({ error: 'Could not verify that you are human. Please try again.' }, 403);
  }

  // --- 3 · Rate limit -----------------------------------------------------
  if (!(await underRateLimit(env.RATE_LIMIT, ip))) {
    return json({ error: 'Too many inquiries from this connection. Please try again later.' }, 429);
  }

  // --- 4 · Validate -------------------------------------------------------
  const name = oneLine(data.name, LIMITS.name);
  const email = oneLine(data.email, LIMITS.email);
  const eventType = oneLine(data.event_type, LIMITS.event_type);
  const eventDate = oneLine(data.event_date, 40);
  const guestCount = oneLine(data.guest_count, 10);
  const message = String(data.message ?? '').trim().slice(0, LIMITS.message);

  if (!name) return json({ error: 'Please tell us your name.' }, 400);
  if (!validEmail(email)) return json({ error: 'Please enter a valid email address.' }, 400);
  if (!eventType || !EVENT_TYPES.has(eventType)) {
    return json({ error: 'Please choose an event type.' }, 400);
  }
  if (guestCount && !/^\d{1,5}$/.test(guestCount)) {
    return json({ error: 'Guest count should be a number.' }, 400);
  }
  if (eventDate && !/^\d{4}-\d{2}-\d{2}$/.test(eventDate)) {
    return json({ error: 'Please use the date picker for the event date.' }, 400);
  }

  // --- 5 · Deliver --------------------------------------------------------
  const to = env.CATERING_TO;
  const from = env.CATERING_FROM;
  const key = env.RESEND_API_KEY;

  if (!to || !from || !key) {
    // Misconfiguration is ours, not the visitor's — and we say nothing about
    // which binding is missing.
    console.error('catering: missing binding', {
      to: !!to, from: !!from, key: !!key,
    });
    return json({ error: 'The inquiry form is temporarily unavailable. Please reach us on Instagram.' }, 503);
  }

  const rows = [
    ['Name', name],
    ['Email', email],
    ['Event type', eventType],
    ['Event date', eventDate || '—'],
    ['Guest count', guestCount || '—'],
  ];

  const html = `
<div style="font-family:'Hanken Grotesk',Helvetica,Arial,sans-serif;color:#26231E;background:#FCFAF4;padding:28px">
  <p style="font:600 12px sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#7C8A6B;margin:0 0 6px">
    Catering inquiry
  </p>
  <h1 style="font:400 26px Georgia,serif;margin:0 0 22px">${esc(name)} — ${esc(eventType)}</h1>
  <table cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:22px">
    ${rows.map(([k, v]) => `
      <tr>
        <td style="padding:7px 22px 7px 0;color:#6A6459;font-size:13px;white-space:nowrap">${esc(k)}</td>
        <td style="padding:7px 0;font-size:15px">${esc(v)}</td>
      </tr>`).join('')}
  </table>
  ${message ? `
    <p style="font:600 12px sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#7C8A6B;margin:0 0 8px">Message</p>
    <div style="background:#F1E9D8;border-left:3px solid #7C8A6B;padding:16px 18px;font-size:15px;line-height:1.6;white-space:pre-wrap">${esc(message)}</div>
  ` : ''}
  <p style="margin:26px 0 0;font-size:12px;color:#6A6459">
    Sent from the catering form at layerssuperfoodbar.com
  </p>
</div>`.trim();

  const text = [
    `Catering inquiry — ${name}`,
    '',
    ...rows.map(([k, v]) => `${k}: ${v}`),
    '',
    message ? `Message:\n${message}` : '(no message)',
    '',
    'Sent from the catering form at layerssuperfoodbar.com',
  ].join('\n');

  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        authorization: `Bearer ${key}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        from,
        to: [to],
        reply_to: email,          // owner hits Reply and reaches the customer
        subject: `Catering inquiry — ${name} (${eventType})`,
        html,
        text,
      }),
      signal: AbortSignal.timeout(8000),
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      console.error('catering: resend failed', res.status, detail.slice(0, 300));
      return json({ error: 'We could not send that just now. Please try again in a moment.' }, 502);
    }
  } catch (err) {
    console.error('catering: send threw', String(err));
    return json({ error: 'We could not send that just now. Please try again in a moment.' }, 502);
  }

  return json({ ok: true });
}

/** Anything other than POST gets a clean, cacheable refusal. */
export async function onRequest(context) {
  if (context.request.method === 'POST') return onRequestPost(context);
  return new Response('Method not allowed', {
    status: 405,
    headers: { allow: 'POST', 'cache-control': 'no-store' },
  });
}
