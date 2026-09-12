/*  Сборка отдельных страниц работ Antiqua Gallery.
 *
 *  Зачем они нужны. Окно работы на главной — быстрый просмотр, но у него нет
 *  своего адреса: ссылку на конкретную картину отправить нельзя, и поисковик
 *  видит одну страницу вместо двадцати четырёх. Эти страницы дают каждой
 *  работе постоянный адрес, собственное превью для мессенджеров и описание
 *  для поиска.
 *
 *  Данные снимаются с docs/antique/index.html в браузере — тот же приём, что
 *  в build-catalogue.js. Второго списка работ в проекте нет и быть не должно:
 *  однажды он разойдётся с сайтом.
 *
 *  Запуск:  node tools/build-work-pages.js
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'docs/antique/index.html');
const OUT_DIR = path.join(ROOT, 'docs/antique/work');
const BASE = 'https://jeylimon.github.io/invest-assistant-bot/antique/';
const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const WA = 'https://wa.me/79219322670';
const TEL = '+79219322670';

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const GROUPS = {
  landscape: { ru: 'Пейзаж и марина', en: 'Landscape & Marine' },
  figure:    { ru: 'Фигура и портрет', en: 'Figure & Portrait' },
  still:     { ru: 'Натюрморт',        en: 'Still Life' },
  abstract:  { ru: 'Абстракция',       en: 'Abstract' }
};

/* ── Состав собрания снимаем с готовой страницы ── */
async function readSite(browser) {
  const page = await browser.newPage();
  await page.goto('file://' + SITE, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const data = await page.evaluate(() => {
    /* META и SRCS объявлены через const на верхнем уровне классического
       скрипта: в window они не попадают, но в области видимости evaluate
       доступны по имени. */
    const meta = META, srcs = SRCS;
    const cards = [...document.querySelectorAll('.gallery-item')].map(el => {
      const frame = el.querySelector('.item-frame');
      const m = (frame.getAttribute('style') || '').match(/--lqip:\s*(url\([^)]*\))/);
      return {
        index: +el.dataset.index,
        group: el.dataset.group,
        sold: el.classList.contains('is-sold'),
        lqip: m ? m[1] : ''
      };
    });
    return { meta, srcs, cards };
  });
  await page.close();

  if (data.meta.length !== data.srcs.length || data.meta.length !== data.cards.length)
    throw new Error('META, SRCS и карточки разошлись: ' +
      [data.meta.length, data.srcs.length, data.cards.length].join(' / '));

  return data.meta.map((m, i) => {
    const card = data.cards.find(c => c.index === i);
    if (!card) throw new Error('нет карточки с data-index=' + i);
    const src = data.srcs[i];
    const file = path.join(ROOT, 'docs/antique', src);
    if (!fs.existsSync(file)) throw new Error('нет файла снимка: ' + src);
    return {
      i,
      n: String(i + 1).padStart(2, '0'),
      slug: path.basename(src).replace(/\.[a-z]+$/i, ''),
      src,
      lqip: card.lqip,
      group: card.group,
      sold: !!(m.sold || card.sold),
      cert: !!m.cert,
      ru: { title: m.ru_title, desc: m.ru_desc },
      en: { title: m.en_title, desc: m.en_desc }
    };
  });
}

/* Ссылка в WhatsApp с заранее набранным текстом — человек не должен
   придумывать, как назвать работу, которой интересуется. */
const waHref = (w, l) => WA + '?text=' + encodeURIComponent(l === 'ru'
  ? 'Здравствуйте! Меня интересует картина «' + w.ru.title + '» (№' + w.n + ')'
  : 'Hello! I am interested in the painting “' + w.en.title + '” (no. ' + w.n + ')');

const t = (ru, en) => `data-ru="${esc(ru)}" data-en="${esc(en)}">${esc(ru)}`;

const CSS = `
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0B0907;--ink2:#131009;--gold:#C4A24A;--gold2:#E0C070;--gold-dim:#6B5A28;
 --cream:#EDE5CF;--cream2:#C2B89E;--muted:#8C8071;--border:rgba(196,162,74,.16)}
html{overflow-x:hidden;scroll-behavior:smooth}
body{background:var(--ink);color:var(--cream);font-family:'Tenor Sans',-apple-system,sans-serif;
 font-size:15px;line-height:1.8;-webkit-font-smoothing:antialiased}
a{color:inherit}
img{max-width:100%;display:block}
.wrap{max-width:1320px;margin:0 auto;padding:0 clamp(20px,5vw,64px)}

/* ── шапка ── */
.top{position:sticky;top:0;z-index:50;background:rgba(11,9,7,.9);backdrop-filter:blur(12px);
 border-bottom:1px solid var(--border)}
.top-in{display:flex;align-items:center;justify-content:space-between;gap:20px;
 padding:16px clamp(20px,5vw,64px);max-width:1320px;margin:0 auto}
.mark{font-family:'Cormorant Garamond',Georgia,serif;font-size:clamp(12px,3.1vw,17px);
 letter-spacing:clamp(.16em,.9vw,.38em);white-space:nowrap;
 color:var(--gold);text-transform:uppercase;text-decoration:none;text-indent:.38em}
.lang{display:flex;gap:2px}
.lang-btn{background:none;border:1px solid transparent;color:var(--muted);cursor:pointer;
 font-family:'Tenor Sans',sans-serif;font-size:10px;letter-spacing:.22em;padding:6px 11px;
 text-transform:uppercase;transition:color .3s,border-color .3s}
.lang-btn.on{color:var(--gold);border-color:rgba(196,162,74,.4)}
.lang-btn:hover{color:var(--gold2)}

/* ── хлебные крошки ── */
.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:11px;
 font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);
 padding:34px 0 0}
.crumbs a{color:var(--muted);text-decoration:none;transition:color .3s}
.crumbs a:hover{color:var(--gold)}
.crumbs i{font-style:normal;color:var(--gold-dim)}

/* ── работа ── */
.work{display:grid;grid-template-columns:minmax(0,1.42fr) minmax(300px,.58fr);
 gap:clamp(34px,5vw,78px);align-items:start;padding:36px 0 40px}
.shot{position:relative;background:#050403;border:1px solid var(--border);
 padding:clamp(16px,2.4vw,34px);overflow:hidden}
.shot::before{content:'';position:absolute;inset:0;background:var(--lqip) center/cover no-repeat;
 filter:blur(30px) brightness(.5);transform:scale(1.15);opacity:.5;transition:opacity .9s ease}
.shot.ready::before{opacity:0}
.shot img{position:relative;width:100%;max-height:76vh;object-fit:contain;margin:0 auto;
 box-shadow:0 40px 90px rgba(0,0,0,.72)}
/* Кадр раскрывается при загрузке — та же манера, что у карточек в собрании. */
.shot{clip-path:inset(0 0 100% 0);transition:clip-path 1.25s cubic-bezier(.22,1,.36,1)}
.shot.in{clip-path:inset(0 0 0 0)}

.side{position:sticky;top:104px}
.eye{display:block;font-size:9.5px;letter-spacing:.32em;text-transform:uppercase;
 color:var(--gold-dim);margin-bottom:22px}
.num{font-family:'Cormorant Garamond',Georgia,serif;font-size:13px;letter-spacing:.3em;
 color:var(--gold);margin-bottom:14px}
h1{font-family:'Cormorant Garamond',Georgia,serif;font-weight:300;
 font-size:clamp(31px,4vw,52px);line-height:1.08;letter-spacing:.035em;
 color:var(--cream);text-wrap:balance;margin-bottom:18px}
.spec{font-size:14px;line-height:1.9;color:var(--cream2);letter-spacing:.02em;margin-bottom:26px}
.cert{display:inline-flex;align-items:center;gap:10px;font-size:10px;letter-spacing:.26em;
 text-transform:uppercase;color:var(--gold);border:1px solid rgba(196,162,74,.4);
 padding:7px 14px;margin-bottom:20px}
.cert::before{content:'';width:6px;height:6px;background:var(--gold);transform:rotate(45deg)}
.rule{width:64px;height:1px;background:var(--gold-dim);margin:0 0 26px}
.price{font-family:'Cormorant Garamond',Georgia,serif;font-size:25px;letter-spacing:.05em;
 color:var(--cream);margin-bottom:26px}
.sold{display:inline-flex;align-items:center;gap:12px;font-size:11px;letter-spacing:.32em;
 text-transform:uppercase;color:var(--gold);border:1px solid rgba(196,162,74,.55);
 background:rgba(8,6,5,.8);padding:11px 19px;margin-bottom:26px}
.sold::before{content:'';width:7px;height:7px;background:var(--gold);transform:rotate(45deg)}
.cta{display:inline-flex;align-items:center;gap:13px;padding:15px 34px;
 border:1px solid var(--gold);color:var(--gold);text-decoration:none;
 font-size:10.5px;letter-spacing:.28em;text-transform:uppercase;
 transition:background .45s,color .45s}
.cta:hover{background:var(--gold);color:var(--ink)}
.tel{display:block;margin-top:18px;font-size:12px;letter-spacing:.14em;color:var(--muted);
 text-decoration:none;transition:color .3s}
.tel:hover{color:var(--gold)}
.copy{display:block;margin-top:14px;background:none;border:none;color:var(--muted);cursor:pointer;
 font-family:'Tenor Sans',sans-serif;font-size:11px;letter-spacing:.2em;text-transform:uppercase;
 padding:0;transition:color .3s}
.copy:hover{color:var(--gold)}

/* ── из того же круга ── */
.more{border-top:1px solid var(--border);padding:48px 0 10px}
.more-t{font-size:10px;letter-spacing:.3em;text-transform:uppercase;color:var(--gold-dim);
 margin-bottom:22px}
.more-row{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(12px,2vw,24px)}
.more-it{position:relative;display:block;text-decoration:none;overflow:hidden;
 aspect-ratio:1;background:#050403}
.more-it img{width:100%;height:100%;object-fit:cover;
 filter:brightness(.72) saturate(.88);transition:transform .8s cubic-bezier(.16,1,.3,1),filter .5s}
.more-it:hover img{transform:scale(1.06);filter:brightness(1) saturate(1)}
.more-it::after{content:'';position:absolute;inset:0;border:1px solid rgba(196,162,74,0);
 transition:border-color .45s}
.more-it:hover::after{border-color:rgba(196,162,74,.55)}
.more-cap{position:absolute;left:0;right:0;bottom:0;padding:11px 12px 12px;
 background:linear-gradient(to top,rgba(8,6,5,.96),transparent);
 font-family:'Cormorant Garamond',Georgia,serif;font-size:15px;letter-spacing:.03em;
 color:var(--cream)}

/* ── листание ── */
.pager{display:flex;justify-content:space-between;gap:18px;align-items:stretch;
 border-top:1px solid var(--border);margin-top:48px;padding:26px 0 70px}
.pg{display:flex;flex-direction:column;gap:7px;text-decoration:none;max-width:46%;
 transition:opacity .3s}
.pg:hover{opacity:.72}
.pg.next{text-align:right;margin-left:auto}
.pg-l{font-size:9.5px;letter-spacing:.28em;text-transform:uppercase;color:var(--gold-dim)}
.pg-n{font-family:'Cormorant Garamond',Georgia,serif;font-size:19px;letter-spacing:.03em;
 color:var(--cream)}

footer{border-top:1px solid var(--border);padding:40px 0 46px;text-align:center}
.foot-mark{font-family:'Cormorant Garamond',Georgia,serif;font-size:15px;letter-spacing:.36em;
 color:var(--gold);text-transform:uppercase;text-indent:.36em;margin-bottom:10px}
.foot-c{font-size:11px;letter-spacing:.16em;color:var(--muted)}

@media(max-width:900px){
  .work{grid-template-columns:1fr;gap:32px;padding-top:24px}
  .side{position:static}
  .shot img{max-height:62vh}
  .more-row{grid-template-columns:repeat(3,1fr);gap:10px}
  .more-cap{font-size:12px;padding:8px 9px 9px}
}
@media(max-width:520px){
  .more-row{grid-template-columns:1fr 1fr}
  .more-row a:nth-child(3){display:none}
}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .shot{clip-path:none}
}
@media print{
  .top,.pager,.more,.cta,.copy,.crumbs{display:none}
  body{background:#fff;color:#000}
}
`;

function page(w, all, byGroup) {
  const rel = '../../';
  const url = BASE + 'work/' + w.slug + '/';
  const gr = GROUPS[w.group] || { ru: 'Собрание', en: 'Collection' };

  const prev = all[(w.i - 1 + all.length) % all.length];
  const next = all[(w.i + 1) % all.length];

  /* Соседи по жанру — тот же отбор, что в окне работы на главной. */
  const peers = byGroup[w.group].filter(x => x.i !== w.i).slice(0, 3);

  const descRu = w.ru.desc + '. ' + (w.sold
    ? 'Работа продана.'
    : 'Цена по запросу. Antiqua Gallery — редкие произведения европейской живописи.');
  const descEn = w.en.desc + '. ' + (w.sold
    ? 'This work has been sold.'
    : 'Price on request. Antiqua Gallery — rare works of European painting.');

  const ld = {
    '@context': 'https://schema.org',
    '@type': 'VisualArtwork',
    name: w.ru.title,
    alternateName: w.en.title,
    image: BASE + w.src,
    url,
    artform: 'Painting',
    description: w.ru.desc,
    offers: {
      '@type': 'Offer',
      url,
      availability: w.sold
        ? 'https://schema.org/SoldOut'
        : 'https://schema.org/InStock',
      priceCurrency: 'RUB',
      price: '0',
      priceValidUntil: '2027-12-31',
      seller: { '@type': 'ArtGallery', name: 'Antiqua Gallery', telephone: TEL }
    }
  };

  return `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>${esc(w.ru.title)} — Antiqua Gallery</title>
<link rel="canonical" href="${esc(url)}">
<meta name="description" content="${esc(descRu)}">
<meta property="og:type"        content="article">
<meta property="og:url"         content="${esc(url)}">
<meta property="og:title"       content="${esc(w.ru.title)} — Antiqua Gallery">
<meta property="og:description" content="${esc(descRu)}">
<meta property="og:image"       content="${esc(BASE + w.src)}">
<meta property="og:locale"      content="ru_RU">
<meta name="twitter:card"       content="summary_large_image">
<meta name="twitter:title"      content="${esc(w.ru.title)} — Antiqua Gallery">
<meta name="twitter:description" content="${esc(descEn)}">
<meta name="twitter:image"      content="${esc(BASE + w.src)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=Tenor+Sans&display=swap" rel="stylesheet">
<script type="application/ld+json">${JSON.stringify(ld)}</script>
<style>${CSS}</style>
</head>
<body>

<header class="top">
  <div class="top-in">
    <a class="mark" href="${rel}">Antiqua Gallery</a>
    <div class="lang">
      <button class="lang-btn on" data-lang="ru" type="button"><span ${t('РУ', 'RU')}</span></button>
      <button class="lang-btn" data-lang="en" type="button">EN</button>
    </div>
  </div>
</header>

<div class="wrap">
  <nav class="crumbs" aria-label="Хлебные крошки" data-ru-label="Хлебные крошки" data-en-label="Breadcrumb">
    <a class="js-coll" href="${rel}" ${t('Собрание', 'Collection')}</a>
    <i>·</i>
    <a class="js-coll" href="${rel}#collection" ${t(gr.ru, gr.en)}</a>
    <i>·</i>
    <span>№ ${w.n}</span>
  </nav>

  <main class="work">
    <div class="shot" id="shot"${w.lqip ? ` style="--lqip:${w.lqip}"` : ''}>
      <img src="${rel}${esc(w.src)}" alt="${esc(w.ru.title)}"
           data-alt-ru="${esc(w.ru.title)}" data-alt-en="${esc(w.en.title)}"
           id="shotImg" fetchpriority="high" decoding="async">
    </div>

    <div class="side">
      <span class="eye">Antiqua Gallery</span>
      <div class="num">№ ${w.n}</div>
      ${w.cert ? `<div class="cert" ${t('Имеется экспертиза', 'Authenticated')}</div>` : ''}
      <h1 ${t(w.ru.title, w.en.title)}</h1>
      <p class="spec" ${t(w.ru.desc, w.en.desc)}</p>
      <div class="rule"></div>
      ${w.sold
        ? `<div class="sold" ${t('Продано', 'Sold')}</div>`
        : `<div class="price" ${t('Цена по запросу', 'Price on Request')}</div>
      <a class="cta" href="${esc(waHref(w, 'ru'))}"
         data-wa-ru="${esc(waHref(w, 'ru'))}" data-wa-en="${esc(waHref(w, 'en'))}"
         target="_blank" rel="noopener"><span ${t('Узнать цену', 'Inquire')}</span><svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" stroke-width="1.2"/><polyline points="8,2 13,7 8,12" stroke="currentColor" stroke-width="1.2" fill="none"/></svg></a>
      <a class="tel" href="tel:${TEL}">${TEL.replace(/^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/, '+7 $1 $2-$3-$4')}</a>`}
      <button class="copy" id="copyBtn" type="button"
              data-done-ru="Ссылка скопирована" data-done-en="Link copied"><span ${t('Скопировать ссылку', 'Copy link')}</span></button>
    </div>
  </main>

${peers.length ? `  <section class="more">
    <div class="more-t" ${t('Из того же круга', 'From the same group')}</div>
    <div class="more-row">
${peers.map(x => `      <a class="more-it" href="../${esc(x.slug)}/">
        <img src="${rel}${esc(x.src)}" alt="${esc(x.ru.title)}" loading="lazy" decoding="async">
        <span class="more-cap" ${t(x.ru.title, x.en.title)}</span>
      </a>`).join('\n')}
    </div>
  </section>` : ''}

  <nav class="pager" aria-label="Листание работ" data-ru-label="Листание работ" data-en-label="Work navigation">
    <a class="pg prev" href="../${esc(prev.slug)}/">
      <span class="pg-l" ${t('← Предыдущая', '← Previous')}</span>
      <span class="pg-n" ${t(prev.ru.title, prev.en.title)}</span>
    </a>
    <a class="pg next" href="../${esc(next.slug)}/">
      <span class="pg-l" ${t('Следующая →', 'Next →')}</span>
      <span class="pg-n" ${t(next.ru.title, next.en.title)}</span>
    </a>
  </nav>
</div>

<footer>
  <div class="foot-mark">Antiqua Gallery</div>
  <div class="foot-c" ${t('© 2026 Все права защищены', '© 2026 All rights reserved')}</div>
</footer>

<script>
(function(){
  var shot = document.getElementById('shot'), img = document.getElementById('shotImg');
  function ready(){ shot.classList.add('ready'); }
  if (img.complete) ready(); else img.addEventListener('load', ready);
  requestAnimationFrame(function(){ requestAnimationFrame(function(){ shot.classList.add('in'); }); });

  /* Язык запоминается: иначе переход с английской страницы работы
     обратно в собрание молча возвращал бы русский. */
  function setLang(l){
    document.querySelectorAll('[data-ru]').forEach(function(el){
      if (el.dataset.en) el.textContent = l === 'ru' ? el.dataset.ru : el.dataset.en;
    });
    document.querySelectorAll('[data-ru-label]').forEach(function(el){
      el.setAttribute('aria-label', l === 'ru' ? el.dataset.ruLabel : el.dataset.enLabel);
    });
    document.querySelectorAll('[data-wa-ru]').forEach(function(a){
      a.href = l === 'ru' ? a.dataset.waRu : a.dataset.waEn;
    });
    if (img.dataset.altEn) img.alt = l === 'ru' ? img.dataset.altRu : img.dataset.altEn;
    document.documentElement.lang = l;
    document.title = (l === 'ru' ? ${JSON.stringify(w.ru.title)} : ${JSON.stringify(w.en.title)}) + ' — Antiqua Gallery';
    document.querySelectorAll('.lang-btn').forEach(function(b){ b.classList.toggle('on', b.dataset.lang === l); });
    /* Ссылки в собрание уносят выбранный язык с собой. */
    document.querySelectorAll('.js-coll').forEach(function(a){
      a.href = a.getAttribute('href').split('?')[0].split('#')[0]
             + (l === 'en' ? '?lang=en' : '')
             + (a.dataset.hash || '');
    });
    try { localStorage.setItem('ag_lang', l); } catch (e) {}
  }
  document.querySelectorAll('.js-coll').forEach(function(a){
    var h = a.getAttribute('href'), i = h.indexOf('#');
    if (i > -1) a.dataset.hash = h.slice(i);
  });
  document.querySelectorAll('.lang-btn').forEach(function(b){
    b.addEventListener('click', function(){ setLang(b.dataset.lang); });
  });
  var start = 'ru';
  try { if (/[?&]lang=en\\b/.test(location.search)) start = 'en';
        else if (localStorage.getItem('ag_lang') === 'en') start = 'en'; } catch (e) {}
  if (start === 'en') setLang('en');

  var btn = document.getElementById('copyBtn'), span = btn.querySelector('span');
  btn.addEventListener('click', function(){
    var url = location.href.split('?')[0];
    var done = function(){
      var ru = document.documentElement.lang === 'ru';
      span.textContent = ru ? btn.dataset.doneRu : btn.dataset.doneEn;
      setTimeout(function(){ span.textContent = ru ? span.dataset.ru : span.dataset.en; }, 2000);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, function(){});
    } else {
      var f = document.createElement('textarea');
      f.value = url; f.setAttribute('readonly', '');
      f.style.position = 'fixed'; f.style.left = '-9999px';
      document.body.appendChild(f); f.select();
      try { document.execCommand('copy'); done(); } catch (e) {}
      document.body.removeChild(f);
    }
  });
})();
</script>
</body>
</html>
`;
}

/* Голый адрес /antique/work/ иначе отдаёт 404 — уводим в собрание. */
const INDEX_STUB = `<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=../">
<link rel="canonical" href="${BASE}">
<title>Antiqua Gallery</title></head>
<body style="background:#0B0907;color:#C4A24A;font-family:Georgia,serif;padding:40px">
<a href="../" style="color:#C4A24A">Перейти к собранию</a></body></html>
`;

function sitemap(works) {
  const urls = [BASE, ...works.map(w => BASE + 'work/' + w.slug + '/')];
  return '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    urls.map(u => `  <url><loc>${u}</loc></url>`).join('\n') +
    '\n</urlset>\n';
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  try {
    console.log('Читаю состав собрания со страницы сайта…');
    const works = await readSite(browser);
    console.log('  работ:', works.length);

    const byGroup = {};
    works.forEach(w => { (byGroup[w.group] = byGroup[w.group] || []).push(w); });

    const slugs = new Set();
    works.forEach(w => {
      if (slugs.has(w.slug)) throw new Error('повторяющийся адрес: ' + w.slug);
      slugs.add(w.slug);
    });

    /* Каталог пересобираем с нуля: работа, убранная с сайта, не должна
       остаться висеть отдельной страницей. */
    if (fs.existsSync(OUT_DIR)) fs.rmSync(OUT_DIR, { recursive: true });
    fs.mkdirSync(OUT_DIR, { recursive: true });

    works.forEach(w => {
      const dir = path.join(OUT_DIR, w.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, 'index.html'), page(w, works, byGroup));
    });
    fs.writeFileSync(path.join(OUT_DIR, 'index.html'), INDEX_STUB);
    fs.writeFileSync(path.join(ROOT, 'docs/antique/sitemap.xml'), sitemap(works));

    console.log('Готово:', works.length, 'страниц → docs/antique/work/<адрес>/');
    console.log('  карта сайта → docs/antique/sitemap.xml');
  } finally {
    await browser.close();
  }
})();
