// Headless-Chrome helpers over the DevTools protocol (Node >= 22, no deps).
//   node tools/dev/cdp.mjs eval <url> <width> <height> <mobile|-> <file.js>   → prints the expression's value
//   node tools/dev/cdp.mjs shot <url> <out.png> <width> <height> [mobile] [reduce]  → full-page screenshot
// The page is scrolled top→bottom first so lazy images load. "reduce" emulates
// prefers-reduced-motion so reveal animations don't hide content in shots.
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [cmd, url, ...rest] = process.argv.slice(2);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const prof = mkdtempSync(join(tmpdir(), 'cdp-'));
const port = 9700 + Math.floor(Math.random() * 250);
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, '--no-first-run', '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pend = new Map();
const send = (m, p = {}) => new Promise((res, rej) => { const i = ++id; pend.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method: m, params: p })); });

async function open(W, H, mobile, reduce) {
  let wsu;
  for (let i = 0; i < 80 && !wsu; i++) { try { wsu = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(x => x.type === 'page')?.webSocketDebuggerUrl; } catch {} await sleep(150); }
  ws = new WebSocket(wsu); await new Promise(r => ws.addEventListener('open', r));
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') console.error('CONSOLE ERROR', JSON.stringify(m.params.args.map(a => a.value ?? a.description)));
    else if (m.method === 'Runtime.exceptionThrown') console.error('EXCEPTION', m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: +W, height: +H, deviceScaleFactor: 1, mobile: !!mobile });
  if (reduce) await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await send('Page.navigate', { url }); await sleep(2500);
}
const evalJs = async expr => { const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails)); return r.result.value; };

try {
  if (cmd === 'eval') {
    const [W, H, mob, file] = rest; await open(W, H, mob === 'mobile', false);
    console.log(await evalJs(readFileSync(file, 'utf8')));
  } else if (cmd === 'shot') {
    const [out, W, H, ...flags] = rest; await open(W, H, flags.includes('mobile'), flags.includes('reduce'));
    await evalJs(`(async()=>{for(let y=0;y<document.body.scrollHeight;y+=innerHeight*0.7){scrollTo(0,y);await new Promise(r=>setTimeout(r,140));}scrollTo(0,0);await new Promise(r=>setTimeout(r,900));})()`);
    const h = await evalJs('Math.ceil(document.documentElement.scrollHeight)');
    await send('Emulation.setDeviceMetricsOverride', { width: +W, height: Math.min(h, 16000), deviceScaleFactor: 1, mobile: flags.includes('mobile') });
    await sleep(700);
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    writeFileSync(out, Buffer.from(shot.data, 'base64')); console.log(out, W + 'x' + h);
  } else { console.error('usage: cdp.mjs eval|shot ...'); process.exitCode = 2; }
} catch (e) { console.error('ERR', e.message); process.exitCode = 1; }
finally { try { ws?.close(); } catch {} chrome.kill('SIGKILL'); setTimeout(() => { try { rmSync(prof, { recursive: true, force: true }); } catch {} }, 400); }
