const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const p = await b.newPage();
  await p.goto('file:///tmp/claude-0/-home-user-invest-assistant-bot/632936ed-7825-5566-b5c3-8ed4d1b7ed35/scratchpad/catalogue.html',
               { waitUntil: 'networkidle' });
  await p.waitForTimeout(2500);
  await p.pdf({ path: '/home/user/invest-assistant-bot/docs/antique/antiqua-gallery-catalogue.pdf',
                format: 'A4', printBackground: true,
                margin: { top:'0', bottom:'0', left:'0', right:'0' } });
  await b.close();
  console.log('PDF готов');
})();
