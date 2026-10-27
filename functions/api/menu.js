/**
 * GET /api/menu — live menu, synced from the Square Catalog API.
 *
 * Design goals, in priority order:
 *   1. Never break the page. Any failure returns the last-known-good menu with
 *      source:"fallback"; the client leaves its pre-rendered menu in place.
 *   2. Be fast. Responses are cached at the edge for SYNC_TTL seconds, so a
 *      burst of visitors costs one Square call, not one per visitor.
 *   3. Never leak credentials. The access token exists only as a binding.
 *   4. Respect the site's menu. Items hidden in content/menu.json are listed
 *      by the build under "hidden" in menu-fallback.json; they are never
 *      served, even though Square still sells them.
 *
 * Required binding:  SQUARE_ACCESS_TOKEN   (secret)
 * Optional bindings: SQUARE_API_BASE       (default https://connect.squareup.com)
 *                    SQUARE_VERSION        (default 2025-01-23)
 *                    MENU_TTL              (default 300 seconds)
 */

const DEFAULT_TTL = 300;
const SQUARE_VERSION = '2025-01-23';

/** Category display order; anything unlisted is appended alphabetically. */
const CATEGORY_ORDER = ['Bowls', 'Smoothies'];

/** Singular noun shown on the card, derived from its category. */
function kindFor(categoryName) {
  if (!categoryName) return '';
  const n = categoryName.trim();
  if (/^bowls?$/i.test(n)) return 'Bowl';
  if (/^smoothies?$/i.test(n)) return 'Smoothie';
  return n.replace(/s$/i, '');
}

/**
 * Square puts the parenthetical qualifier in the item name
 * ("Strawesome (Skin Health & Antioxidant)"). The prototype renders the two
 * parts differently, so split them here rather than in the browser.
 */
function splitName(raw) {
  const m = /^(.*?)\s*\(([^()]*)\)\s*$/.exec(raw || '');
  return m ? { name: m[1].trim(), note: m[2].trim() } : { name: (raw || '').trim(), note: '' };
}

function toDollars(money) {
  if (!money || typeof money.amount !== 'number') return null;
  // Square returns the smallest currency unit; USD -> cents.
  return (money.amount / 100).toFixed(2);
}

/** Cheapest variation wins as the displayed "from" price. */
function priceOf(item) {
  const variations = item?.item_data?.variations || [];
  let best = null;
  for (const v of variations) {
    const p = toDollars(v?.item_variation_data?.price_money);
    if (p !== null && (best === null || parseFloat(p) < parseFloat(best))) best = p;
  }
  return best;
}

function soldOutOf(item) {
  const variations = item?.item_data?.variations || [];
  if (!variations.length) return false;
  // Sold out only when every variation is sold out at every location.
  return variations.every((v) => {
    const overrides = v?.item_variation_data?.location_overrides || [];
    return overrides.length > 0 && overrides.every((o) => o.sold_out === true);
  });
}

function caloriesOf(item) {
  const c = item?.item_data?.food_and_beverage_details?.calorie_count;
  return typeof c === 'number' ? c : null;
}

async function fetchFallback(request) {
  try {
    const url = new URL('/assets/data/menu-fallback.json', request.url);
    const res = await fetch(url.toString(), { cf: { cacheTtl: 3600 } });
    if (!res.ok) return null;
    const json = await res.json();
    json.source = 'fallback';
    return json;
  } catch {
    return null;
  }
}

function jsonResponse(body, { status = 200, ttl = 0 } = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': ttl > 0
        ? `public, max-age=60, s-maxage=${ttl}, stale-while-revalidate=600`
        : 'no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const ttl = Number(env.MENU_TTL) || DEFAULT_TTL;

  // --- edge cache ---------------------------------------------------------
  const cache = caches.default;
  const cacheKey = new Request(new URL('/api/menu', request.url).toString(), { method: 'GET' });
  const hit = await cache.match(cacheKey);
  if (hit) return hit;

  const token = env.SQUARE_ACCESS_TOKEN;
  if (!token) {
    // Not wired up yet — serve the fallback rather than an error.
    const fb = await fetchFallback(request);
    return jsonResponse(fb || { source: 'fallback', categories: [] }, { ttl: 60 });
  }

  const base = env.SQUARE_API_BASE || 'https://connect.squareup.com';
  const version = env.SQUARE_VERSION || SQUARE_VERSION;
  // The built menu (also the fallback below) names the items hidden on the site.
  const fallback = await fetchFallback(request);
  const hidden = new Set(Array.isArray(fallback?.hidden) ? fallback.hidden : []);

  try {
    const res = await fetch(
      `${base}/v2/catalog/list?types=ITEM,CATEGORY,IMAGE`,
      {
        headers: {
          authorization: `Bearer ${token}`,
          'Square-Version': version,
          accept: 'application/json',
        },
        // Guard against a hung upstream holding the request open.
        signal: AbortSignal.timeout(6000),
      }
    );

    if (!res.ok) throw new Error(`square ${res.status}`);
    const data = await res.json();
    const objects = data.objects || [];

    const categories = new Map();   // id -> name
    const images = new Map();       // id -> url
    const items = [];

    for (const o of objects) {
      if (o.type === 'CATEGORY') categories.set(o.id, o.category_data?.name || '');
      else if (o.type === 'IMAGE') images.set(o.id, o.image_data?.url || '');
      else if (o.type === 'ITEM' && !o.is_deleted) items.push(o);
    }

    const grouped = new Map();      // categoryName -> items[]

    for (const item of items) {
      if (hidden.has(item.id)) continue;
      const d = item.item_data || {};
      // Square supports both the legacy single category_id and the newer list.
      const catId = d.category_id || d.categories?.[0]?.id || d.reporting_category?.id || null;
      const catName = (catId && categories.get(catId)) || 'Menu';
      const { name, note } = splitName(d.name);
      const imageId = d.image_ids?.[0];

      const entry = {
        id: item.id,
        kind: kindFor(catName),
        name,
        note,
        price: priceOf(item),
        calories: caloriesOf(item),
        image: (imageId && images.get(imageId)) || null,
        soldOut: soldOutOf(item),
      };

      if (!grouped.has(catName)) grouped.set(catName, []);
      grouped.get(catName).push(entry);
    }

    if (!grouped.size) throw new Error('square returned no items');

    const ordered = [...grouped.keys()].sort((a, b) => {
      const ia = CATEGORY_ORDER.indexOf(a), ib = CATEGORY_ORDER.indexOf(b);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    });

    const payload = {
      source: 'square',
      syncedAt: new Date().toISOString(),
      categories: ordered.map((name) => ({ name, items: grouped.get(name) })),
    };

    const response = jsonResponse(payload, { ttl });
    context.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  } catch (err) {
    // Square unreachable, rate-limited, or shape-shifted. Serve last-known-good.
    const fb = fallback || await fetchFallback(request);
    if (fb) return jsonResponse(fb, { ttl: 60 });
    return jsonResponse(
      { source: 'error', categories: [], error: 'menu temporarily unavailable' },
      { status: 503 }
    );
  }
}
