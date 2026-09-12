/*  Сборка печатного каталога Antiqua Gallery.
 *
 *  Данные берутся не из отдельного файла, а прямо со страницы сайта: скрипт
 *  открывает docs/antique/index.html, снимает с неё состав собрания и по нему
 *  верстает каталог. Поэтому каталог не может разойтись с сайтом — именно это
 *  и случилось с прежней версией, где осталось 22 работы вместо 24.
 *
 *  Запуск:  node tools/build-catalogue.js
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const { execFileSync } = require('child_process');
const os = require('os');

const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'docs/antique/index.html');
const OUT_PDF = path.join(ROOT, 'docs/antique/antiqua-gallery-catalogue.pdf');
const OUT_HTML = path.join(__dirname, '.catalogue.html');
const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/* ── Шрифты. Тянем те же, что на сайте, и вшиваем в файл base64: иначе в PDF
      попадут не они, а подстановка системы. Нет сети — печатаем Georgia. ── */
const FONT_CSS_URL = 'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,400&family=Tenor+Sans&display=swap';
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

function get(url, binary) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': UA } }, res => {
      if (res.statusCode !== 200) return reject(new Error(url + ' → ' + res.statusCode));
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve(binary ? Buffer.concat(chunks) : Buffer.concat(chunks).toString('utf8')));
    }).on('error', reject);
  });
}

async function fontCss() {
  try {
    let css = await get(FONT_CSS_URL, false);
    const urls = [...new Set(css.match(/https:\/\/fonts\.gstatic\.com\/[^)]+/g) || [])];
    for (const u of urls) {
      const buf = await get(u, true);
      css = css.split(u).join('data:font/woff2;base64,' + buf.toString('base64'));
    }
    return css;
  } catch (e) {
    console.warn('  шрифты не скачались (' + e.message + '), печатаем системными');
    return '';
  }
}

/* ── Состав собрания снимаем с готовой страницы ── */
async function readSite(browser) {
  const page = await browser.newPage();
  await page.goto('file://' + SITE, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const data = await page.evaluate(() => {
    const ru = el => el ? (el.getAttribute('data-ru') || el.textContent).trim() : '';
    const paintings = [...document.querySelectorAll('.gallery-item')].map((g, i) => ({
      n: i + 1,
      group: g.dataset.group,
      sold: g.classList.contains('is-sold'),
      src: g.querySelector('img').getAttribute('src'),
      title: ru(g.querySelector('.item-name span')),
      desc: ru(g.querySelector('.item-info span')),
      cert: !!g.querySelector('.cert')
    }));
    const lot = sec => {
      const root = document.querySelector('#' + sec + ' .lot-lot');
      if (!root) return null;
      return {
        src: root.querySelector('.lot-frame--main img').getAttribute('src'),
        title: ru(root.querySelector('.lot-title')),
        story: ru(root.querySelector('.lot-story')),
        spec: [...root.querySelectorAll('.lot-spec > div')].map(d => [
          ru(d.querySelector('dt')), ru(d.querySelector('dd'))
        ])
      };
    };
    const editions = [...document.querySelectorAll('.ed-item')].map(e => ({
      src: e.querySelector('img').getAttribute('src'),
      title: ru(e.querySelector('.ed-title')),
      desc: ru(e.querySelector('.ed-spec span') || e.querySelector('.ed-spec'))
    }));
    const sheets = [...document.querySelectorAll('.lot-sheet')].map(f => ({
      src: f.querySelector('img').getAttribute('src'),
      cap: ru(f.querySelector('figcaption'))
    }));
    return {
      paintings, editions, sheets,
      objects: lot('objects'),
      philately: lot('philately'),
      note: {
        objects: ru(document.querySelector('#objects .lot-note')),
        editions: ru(document.querySelector('#editions .ed-note')),
        philately: ru(document.querySelector('#philately .lot-note'))
      },
      phone: (document.querySelector('.contact-phone') || {}).textContent || ''
    };
  });
  await page.close();
  return data;
}

const GROUPS = {
  landscape: 'Пейзаж и марина',
  figure: 'Фигура и портрет',
  still: 'Натюрморт',
  abstract: 'Абстракция'
};

/* Каталог скачивают, поэтому снимки для печати пережимаем: при ширине листа
   в 150 мм больше 1100 пикселей по длинной стороне не нужно, а вес файла
   падает примерно вдвое. Нет python3 — берём исходники как есть. */
function prepareImages(d) {
  const all = [];
  const walk = o => { if (o && o.src) all.push(o.src); };
  d.paintings.forEach(walk); d.editions.forEach(walk); d.sheets.forEach(walk);
  walk(d.objects); walk(d.philately);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'antiqua-cat-'));
  try {
    execFileSync('python3', ['-c', `
import sys, os
from PIL import Image
root, out = sys.argv[1], sys.argv[2]
for rel in sys.argv[3:]:
    im = Image.open(os.path.join(root, rel)).convert('RGB')
    im.thumbnail((1100, 1100), Image.LANCZOS)
    dst = os.path.join(out, rel.replace('/', '_'))
    im.save(dst, 'JPEG', quality=78, optimize=True, progressive=True)
`, path.join(ROOT, 'docs/antique'), dir, ...all], { stdio: ['ignore', 'ignore', 'pipe'] });
    console.log('  снимки пережаты для печати:', all.length);
    return dir;
  } catch (e) {
    console.warn('  пережать не удалось, беру исходники');
    return null;
  }
}

function buildHtml(d, fonts, printDir) {
  const base = 'file://' + path.join(ROOT, 'docs/antique') + '/';
  const img = src => printDir
    ? 'file://' + path.join(printDir, src.replace(/\//g, '_'))
    : base + src;
  const byGroup = g => d.paintings.filter(p => p.group === g).length;

  const plate = (o, eyebrow) => `
<section class="page plate">
  <div class="plate-top">${eyebrow ? `<span class="eyebrow">${esc(eyebrow)}</span>` : ''}
    <span class="plate-n">${o.n ? String(o.n).padStart(2, '0') : ''}</span></div>
  <div class="plate-img"><img src="${esc(img(o.src))}" alt=""></div>
  <div class="plate-cap">
    <h2>${esc(o.title)}</h2>
    <p class="spec">${esc(o.desc || '')}</p>
    <p class="price">${o.sold ? 'Работа продана' : 'Цена по запросу'}${o.cert ? ' · имеется экспертиза' : ''}</p>
  </div>
</section>`;

  const lotPage = (o, eyebrow, note) => `
<section class="page plate">
  <div class="plate-top"><span class="eyebrow">${esc(eyebrow)}</span><span class="plate-n"></span></div>
  <div class="plate-img"><img src="${esc(img(o.src))}" alt=""></div>
  <div class="plate-cap">
    <h2>${esc(o.title)}</h2>
    <table class="spec-tbl">${o.spec.map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>
    ${o.story ? `<p class="story">${esc(o.story)}</p>` : ''}
    <p class="price">Цена по запросу</p>
  </div>
</section>`;

  const pages = [];

  /* Обложка */
  pages.push(`
<section class="page cover">
  <div class="cover-frame"><div class="cover-frame-in"></div>
    <div class="cover-mid">
      <div class="cover-name">Antiqua</div>
      <div class="cover-name it">Gallery</div>
      <div class="cover-rule"></div>
      <div class="cover-sub">Собрание живописи,<br>предметов и графики</div>
    </div>
    <div class="cover-foot">Каталог · ${new Date().getFullYear()}</div>
  </div>
</section>`);

  /* Содержание */
  pages.push(`
<section class="page contents">
  <div class="c-head"><span class="eyebrow">Каталог собрания</span><h1>Содержание</h1></div>
  <table class="toc">
    <tr><td>Живопись</td><td class="dots"></td><td class="num">${d.paintings.length}</td></tr>
    ${Object.entries(GROUPS).map(([k, v]) =>
      `<tr class="sub"><td>${esc(v)}</td><td class="dots"></td><td class="num">${byGroup(k)}</td></tr>`).join('')}
    <tr><td>Предметы интерьера</td><td class="dots"></td><td class="num">${d.objects ? 1 : 0}</td></tr>
    <tr><td>Тиражная графика</td><td class="dots"></td><td class="num">${d.editions.length}</td></tr>
    <tr><td>Почтовые марки</td><td class="dots"></td><td class="num">${d.philately ? 1 : 0}</td></tr>
  </table>
  <p class="c-note">Каждая работа в разделе живописи существует в одном экземпляре.
  Тиражная графика вынесена отдельно, её тираж указан на листе.
  Цены сообщаются по запросу.</p>
</section>`);

  /* Живопись — по жанрам, внутри жанра в порядке собрания */
  Object.entries(GROUPS).forEach(([key, name]) => {
    const list = d.paintings.filter(p => p.group === key);
    list.forEach((p, i) => pages.push(plate(p, i === 0 ? 'Живопись · ' + name : '')));
  });

  if (d.objects) pages.push(lotPage(d.objects, 'Предметы интерьера'));
  d.editions.forEach((e, i) => pages.push(plate(
    { ...e, n: i + 1 }, i === 0 ? 'Тиражная графика' : '')));
  if (d.philately) pages.push(lotPage(d.philately, 'Почтовые марки'));

  /* Листы альбома — по два на страницу */
  for (let i = 0; i < d.sheets.length; i += 2) {
    const pair = d.sheets.slice(i, i + 2);
    pages.push(`
<section class="page plate">
  <div class="plate-top"><span class="eyebrow">${i === 0 ? 'Почтовые марки · листы альбома' : ''}</span><span class="plate-n"></span></div>
  <div class="sheets">${pair.map(sh =>
    `<figure><img src="${esc(img(sh.src))}" alt=""><figcaption>${esc(sh.cap)}</figcaption></figure>`).join('')}</div>
</section>`);
  }

  /* Контакты */
  pages.push(`
<section class="page contact">
  <div class="cover-frame"><div class="cover-frame-in"></div>
    <div class="cover-mid">
      <div class="cover-name">Antiqua</div>
      <div class="cover-name it">Gallery</div>
      <div class="cover-rule"></div>
      <div class="ct-phone">${esc(d.phone.trim())}</div>
      <div class="ct-line">WhatsApp · по тому же номеру</div>
      <div class="ct-line">jeylimon.github.io/invest-assistant-bot/antique</div>
      <div class="ct-small">Работы с независимым экспертным заключением отмечены в описании.<br>
      Договор купли-продажи и страховка входят в стоимость.</div>
    </div>
    <div class="cover-foot">Каталог составлен ${new Date().toLocaleDateString('ru-RU')}</div>
  </div>
</section>`);

  return `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Antiqua Gallery — каталог собрания</title>
<style>
${fonts}
@page { size: A4; margin: 0 }
*{margin:0;padding:0;box-sizing:border-box}
:root{--ink:#0B0907;--ink2:#131009;--gold:#C4A24A;--gold2:#E0C070;--gold-dim:#6B5A28;
--cream:#EDE5CF;--cream2:#C2B89E;--muted:#8C8071}
body{background:var(--ink);color:var(--cream);
  font-family:'Tenor Sans',Georgia,serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{width:210mm;height:297mm;position:relative;overflow:hidden;background:var(--ink);
  page-break-after:always;display:flex;flex-direction:column}

/* ── Обложка и контакты ── */
.cover,.contact{padding:14mm}
.cover-frame{position:relative;flex:1;border:1px solid var(--gold);
  display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16mm}
.cover-frame-in{position:absolute;inset:3mm;border:1px solid rgba(196,162,74,.35)}
.cover-mid{text-align:center;position:relative}
.cover-name{font-family:'Cormorant Garamond',Georgia,serif;font-weight:300;font-size:44pt;
  letter-spacing:.16em;text-transform:uppercase;color:var(--cream);line-height:1.06}
.cover-name.it{font-style:italic;color:var(--gold-pale,#F0E4C0)}
.cover-rule{width:26mm;height:1px;background:var(--gold);margin:9mm auto}
.cover-sub{font-size:9pt;letter-spacing:.34em;text-transform:uppercase;color:var(--cream2);line-height:2}
.cover-foot{position:absolute;bottom:10mm;left:0;right:0;text-align:center;
  font-size:7.5pt;letter-spacing:.3em;text-transform:uppercase;color:var(--gold-dim)}
.ct-phone{font-family:'Cormorant Garamond',Georgia,serif;font-size:24pt;color:var(--gold);
  letter-spacing:.06em;margin-bottom:6mm}
.ct-line{font-size:8pt;letter-spacing:.2em;text-transform:uppercase;color:var(--cream2);line-height:2.2}
.ct-small{margin-top:10mm;font-size:7.5pt;letter-spacing:.08em;color:var(--muted);line-height:2}

/* ── Содержание ── */
.contents{padding:26mm 24mm}
.c-head{text-align:center;margin-bottom:16mm}
.eyebrow{font-size:7.5pt;letter-spacing:.42em;text-transform:uppercase;color:var(--gold)}
.c-head h1{font-family:'Cormorant Garamond',Georgia,serif;font-weight:300;font-size:30pt;
  letter-spacing:.1em;text-transform:uppercase;color:var(--cream);margin-top:5mm}
.toc{width:100%;border-collapse:collapse;font-size:11pt}
.toc td{padding:3.4mm 0;vertical-align:baseline;white-space:nowrap;
  font-family:'Cormorant Garamond',Georgia,serif;color:var(--cream)}
.toc tr.sub td{font-family:'Tenor Sans',Georgia,serif;font-size:8.5pt;
  letter-spacing:.16em;text-transform:uppercase;color:var(--cream2);padding:1.9mm 0 1.9mm 8mm}
.toc .dots{width:100%;border-bottom:1px dotted rgba(196,162,74,.35)}
.toc .num{text-align:right;padding-left:5mm;color:var(--gold);font-variant-numeric:tabular-nums}
.c-note{margin-top:18mm;padding-top:6mm;border-top:1px solid rgba(196,162,74,.22);
  font-size:8.5pt;line-height:2;color:var(--muted);letter-spacing:.04em}

/* ── Лист с работой ── */
.plate{padding:16mm 18mm 14mm}
.plate-top{display:flex;justify-content:space-between;align-items:baseline;
  padding-bottom:4mm;border-bottom:1px solid rgba(196,162,74,.22);min-height:7mm}
.plate-n{font-family:'Cormorant Garamond',Georgia,serif;font-size:13pt;
  letter-spacing:.26em;color:var(--gold)}
.plate-img{flex:1;display:flex;align-items:center;justify-content:center;padding:9mm 0}
.plate-img img{max-width:100%;max-height:165mm;display:block;
  box-shadow:0 6mm 18mm rgba(0,0,0,.7)}
.plate-cap{border-top:1px solid rgba(196,162,74,.22);padding-top:6mm}
.plate-cap h2{font-family:'Cormorant Garamond',Georgia,serif;font-weight:300;font-size:20pt;
  letter-spacing:.05em;color:var(--cream);line-height:1.2}
.spec{font-size:8pt;letter-spacing:.16em;text-transform:uppercase;color:var(--cream2);margin-top:3mm}
.price{font-size:7.5pt;letter-spacing:.3em;text-transform:uppercase;color:var(--gold);margin-top:4mm}
.story{font-size:8.5pt;line-height:1.95;color:var(--cream2);margin-top:4mm;
  border-left:1px solid var(--gold-dim);padding-left:4mm}
.spec-tbl{width:100%;border-collapse:collapse;margin-top:4mm}
.spec-tbl td{padding:1.8mm 0;font-size:8.5pt;color:var(--cream2);
  border-bottom:1px solid rgba(196,162,74,.14)}
.spec-tbl td:first-child{width:40mm;font-size:7.5pt;letter-spacing:.2em;
  text-transform:uppercase;color:var(--muted)}
.sheets{flex:1;display:flex;gap:8mm;align-items:center;justify-content:center;padding:8mm 0}
.sheets figure{flex:1;text-align:center}
.sheets img{max-width:100%;max-height:150mm;box-shadow:0 4mm 14mm rgba(0,0,0,.6)}
.sheets figcaption{margin-top:4mm;font-size:7.5pt;letter-spacing:.2em;
  text-transform:uppercase;color:var(--muted)}
</style></head><body>
${pages.join('\n')}
</body></html>`;
}

(async () => {
  console.log('Шрифты…');
  const fonts = await fontCss();
  const browser = await chromium.launch({ executablePath: CHROME });

  console.log('Читаю состав собрания со страницы сайта…');
  const d = await readSite(browser);
  console.log(`  живопись ${d.paintings.length} · предметы ${d.objects ? 1 : 0} · ` +
              `графика ${d.editions.length} · марки ${d.philately ? 1 : 0} · листов ${d.sheets.length}`);

  const printDir = prepareImages(d);
  const html = buildHtml(d, fonts, printDir);
  fs.writeFileSync(OUT_HTML, html);

  const page = await browser.newPage();
  const missing = [];
  page.on('requestfailed', r => missing.push(r.url().slice(-40)));
  await page.goto('file://' + OUT_HTML, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1200);

  const bad = await page.evaluate(() =>
    [...document.images].filter(i => !i.complete || !i.naturalWidth).length);
  if (bad || missing.length) throw new Error('не загрузились изображения: ' + bad + ' ' + missing.join(', '));

  await page.pdf({ path: OUT_PDF, format: 'A4', printBackground: true,
                   margin: { top: '0', bottom: '0', left: '0', right: '0' } });
  await browser.close();

  const kb = Math.round(fs.statSync(OUT_PDF).size / 1024);
  const pages = html.split('class="page').length - 1;
  console.log(`Готово: ${pages} страниц, ${kb} КБ → docs/antique/antiqua-gallery-catalogue.pdf`);
})().catch(e => { console.error('ОШИБКА:', e.message); process.exit(1); });
