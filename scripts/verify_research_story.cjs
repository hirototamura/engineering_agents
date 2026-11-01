/* Verify the actual article, interactions and local evidence navigation. */
const {chromium} = require(process.env.RESEARCH_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const {pathToFileURL} = require('url');
(async () => {
  const dir = path.resolve(process.argv[2]);
  const browser = await chromium.launch({
    executablePath: process.env.RESEARCH_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--allow-file-access-from-files']
  });
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [], checks = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.join(dir, 'index.html')).href);
  await page.waitForFunction(() => document.querySelectorAll('#case-grid div').length === 12);
  assert.equal(await page.locator('#steps button').count(), 6);
  assert((await page.locator('#result-list').innerText()).includes('0.883341'));
  assert.equal(await page.locator('#factorial .bestcell strong').innerText(), '0.991382000');
  await page.locator('#steps button').last().click();
  assert((await page.locator('#stepdetail').innerText()).includes('next question'));
  assert.equal(await page.locator('#steps button[aria-pressed=true]').count(), 1);
  checks.push('measured scores, factorial isolation and six-stage explorer');
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({path: path.join(dir, 'preview-overview.png')});
  await page.locator('#gap-chart').scrollIntoViewIfNeeded();
  await page.screenshot({path: path.join(dir, 'preview-results.png')});
  await page.locator('#run-select').selectOption('0');
  assert.equal(await page.locator('#round-slider').getAttribute('max'), '10');
  await page.locator('#round-slider').evaluate(el => {el.value = 10; el.dispatchEvent(new Event('input'));});
  assert((await page.locator('#round-detail').innerText()).includes('0.990616500'));
  await page.locator('#run-select').selectOption('1');
  await page.locator('#round-slider').evaluate(el => {el.value = 4; el.dispatchEvent(new Event('input'));});
  assert((await page.locator('#round-detail').innerText()).includes('0.991382000'));
  checks.push('both campaign charts retain side-cell best');
  await page.locator('#replay-time').evaluate(el => {el.value = 6; el.dispatchEvent(new Event('input'));});
  assert((await page.locator('#replay-0').innerText()).includes('t=6.000 s'));
  assert((await page.locator('#replay-1').innerText()).includes('t=4.725 s'));
  await page.locator('#cube-0').scrollIntoViewIfNeeded();
  await page.screenshot({path: path.join(dir, 'preview-replay-endpoint.png')});
  await page.locator('#play').click();
  await page.waitForTimeout(300);
  assert(Number(await page.locator('#replay-time').inputValue()) > 0);
  await page.locator('#play').click();
  await page.locator('#case-run').selectOption('0');
  assert((await page.locator('#case-detail').innerText()).includes('0.017833'));
  await page.locator('#case-run').selectOption('1');
  assert((await page.locator('#case-detail').innerText()).includes('lost_balance'));
  assert.equal(await page.locator('#case-grid .fail').count(), 1);
  assert.equal(await page.locator('#case-grid .uncertain').count(), 1);
  checks.push('actual replay endpoints, finite play, and distinct confirmation failures');
  const links = await page.locator('a[href]').evaluateAll(nodes => nodes.map(n => n.href));
  for (const link of links) {
    if (!link.startsWith('file:')) continue;
    const url = new URL(link);
    assert(fs.existsSync(decodeURIComponent(url.pathname)), link);
    if (url.hash && url.pathname.endsWith('/index.html') && url.pathname.includes('research-story')) {
      assert(await page.locator(url.hash).count(), link);
    }
  }
  checks.push('all local evidence and language destinations exist');
  assert(!(await page.locator('svg').evaluateAll(nodes => nodes.some(n => /NaN|Infinity/.test(n.outerHTML)))));
  for (const width of [390, 320]) {
    await page.setViewportSize({width, height: 844});
    await page.evaluate(() => scrollTo(0, 0));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert(await page.locator('.mobile-flow').isVisible());
    await page.screenshot({path: path.join(dir, `preview-mobile-${width}.png`)});
  }
  checks.push('390px and 320px layout with local chart scrolling');
  await page.goto(pathToFileURL(path.join(dir, 'index.ja.html')).href);
  assert.equal(await page.locator('html').getAttribute('lang'), 'ja');
  assert((await page.locator('#stepdetail').innerText()).includes('固定'));
  assert((await page.locator('h1').innerText()).includes('証拠'));
  await page.screenshot({path: path.join(dir, 'preview-japanese-mobile.png')});
  const workspace = path.resolve(dir, '../../../../..');
  const en = path.join(workspace, 'reports/en/items/balancing-cube-research-story.html');
  if (fs.existsSync(en)) {
    await page.goto(pathToFileURL(en).href);
    await page.locator('#report-language-switch a').first().click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'ja');
    await page.locator('#report-language-switch a').first().click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    await page.locator('#report-language-switch a').nth(1).click();
    assert(page.url().includes('/reports/en/index.html'));
    checks.push('catalog reading-copy native language switch and return link');
  }
  assert.deepEqual(errors, []);
  await browser.close();
  const result = {passed: true, checked_at: new Date().toISOString(), checks, errors};
  fs.writeFileSync(path.join(dir, 'browser-qa.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
})().catch(error => {console.error(error); process.exit(1);});
