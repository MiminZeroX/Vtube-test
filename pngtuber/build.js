// Draws an original chibi cat-boy PNGTuber (4 states) as SVG and rasterises it.
// Usage: node pngtuber/build.js
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const C = {
  line: '#5a3326', hair: '#fff4e3', hairShade: '#f6d9bd', streak: '#f6953a', streakShade: '#e2731f',
  ear: '#f6953a', earIn: '#ffd9cf', skin: '#ffeede', skinShade: '#f9cdb8', blush: '#ff9d9d',
  irisTop: '#0c5a52', irisMid: '#1fae7c', irisBot: '#a8f58a', shirt: '#ffffff', shirtShade: '#dfe9f2',
  collar: '#f6953a', bow: '#2fb3a3', bowShade: '#1f8f86', bell: '#ffd34d', bellShade: '#e9a520',
  mouth: '#8a2f3d', tongue: '#ff8f9a',
};
const SW = 6; // outline width

const BACK_HAIR = `M500,200 C330,195 215,300 215,450 C212,520 190,580 160,625 C200,632 228,618 245,598
 C238,650 215,690 190,715 C240,728 285,706 305,676 C312,712 300,742 285,762 C340,760 380,725 392,690
 L608,690 C620,725 660,760 715,762 C700,742 688,712 695,676 C715,706 760,728 810,715
 C785,690 762,650 755,598 C772,618 800,632 840,625 C810,580 788,520 785,450 C785,300 670,195 500,200 Z`;
const FACE = `M292,440 C292,320 708,320 708,440 C708,560 615,648 500,652 C385,648 292,560 292,440 Z`;
const BANGS = `M500,188 C335,188 262,320 266,468 C264,530 276,585 298,622 C312,570 322,505 336,452
 Q346,405 362,384 Q366,420 390,452 Q402,402 432,372 Q442,432 478,474 Q496,412 522,374
 Q536,428 568,460 Q590,412 602,378 Q626,418 652,446 Q656,402 650,384 Q666,420 664,452
 C678,505 688,570 702,622 C724,585 736,530 734,468 C738,320 665,188 500,188 Z`;
const STREAK = `M548,186 L640,205 L668,300 L664,452 L652,446 Q626,418 602,378 Q590,412 568,460 Q536,428 522,374 Q520,270 548,186 Z`;
const EAR = `M262,345 C215,250 205,160 232,92 C320,112 400,165 452,238 Z`;
const EAR_IN = `M282,300 C255,235 248,180 258,138 C315,158 365,195 400,240 Z`;
const EAR_FLUFF = `M285,318 L300,262 L318,296 L338,246 L352,286 L378,246 L384,290 L410,262 L405,300 Z`;
const EYE = `M346,508 Q398,440 458,500 Q462,566 400,578 Q342,568 346,508 Z`;

const mirror = (s) => `<g transform="translate(1000,0) scale(-1,1)">${s}</g>`;
const both = (s) => s + mirror(s);
const P = (d, fill, extra = '') => `<path d="${d}" fill="${fill}" stroke="${C.line}" stroke-width="${SW}" stroke-linejoin="round" stroke-linecap="round" ${extra}/>`;

function eyeOpen() {
  return `<g>
    <path d="${EYE}" fill="#fff"/>
    <g clip-path="url(#eyeClip)">
      <ellipse cx="402" cy="516" rx="47" ry="60" fill="url(#iris)"/>
      <ellipse cx="402" cy="520" rx="47" ry="60" fill="none" stroke="${C.irisTop}" stroke-width="7" opacity=".7"/>
      <ellipse cx="402" cy="512" rx="19" ry="29" fill="#06302f"/>
      <ellipse cx="402" cy="556" rx="30" ry="14" fill="#eaffc0" opacity=".55"/>
      <path d="M340,470 H470 V500 Q400,470 340,505 Z" fill="#06302f" opacity=".45"/>
    </g>
    <path d="M340,512 Q352,462 400,456 Q446,456 462,502" fill="none" stroke="${C.line}" stroke-width="15" stroke-linecap="round"/>
    <path d="M343,508 L322,496 M350,486 L334,468" fill="none" stroke="${C.line}" stroke-width="8" stroke-linecap="round"/>
    <path d="M372,580 Q400,586 428,578" fill="none" stroke="${C.line}" stroke-width="4" stroke-linecap="round" opacity=".7"/>
  </g>`;
}
// highlights are not mirrored so both eyes catch the light from the same side
const eyeShine = (dx) => `<g transform="translate(${dx},0)"><circle cx="382" cy="492" r="15" fill="#fff"/><circle cx="424" cy="546" r="7" fill="#fff"/><circle cx="366" cy="518" r="4.5" fill="#fff"/></g>`;
const eyeClosed = `<g><path d="M344,522 Q400,566 458,520" fill="none" stroke="${C.line}" stroke-width="12" stroke-linecap="round"/>
  <path d="M346,524 L326,536 M360,540 L346,556" fill="none" stroke="${C.line}" stroke-width="7" stroke-linecap="round"/></g>`;

const mouthClosed = `<path d="M474,596 Q487,612 500,598 Q513,612 526,596" fill="none" stroke="${C.line}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>`;
const mouthOpen = `<g><clipPath id="mClip"><path d="M468,592 Q500,584 532,592 Q530,634 500,638 Q470,634 468,592 Z"/></clipPath>
  ${P('M468,592 Q500,584 532,592 Q530,634 500,638 Q470,634 468,592 Z', C.mouth, 'stroke-width="5"')}
  <g clip-path="url(#mClip)"><ellipse cx="500" cy="638" rx="24" ry="16" fill="${C.tongue}"/>
  <path d="M474,588 L483,606 L492,588 Z M508,588 L517,606 L526,588 Z" fill="#fff"/></g></g>`;

function svg({ eyes, mouth }, bg = false) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">
<defs>
  <linearGradient id="iris" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.irisTop}"/><stop offset=".55" stop-color="${C.irisMid}"/><stop offset="1" stop-color="${C.irisBot}"/></linearGradient>
  <linearGradient id="hairG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.hair}"/><stop offset=".7" stop-color="${C.hair}"/><stop offset="1" stop-color="#ffd9a8"/></linearGradient>
  <linearGradient id="backG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.hairShade}"/><stop offset=".55" stop-color="#f9cfa0"/><stop offset="1" stop-color="${C.streak}"/></linearGradient>
  <linearGradient id="streakG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.streakShade}"/><stop offset="1" stop-color="#ffb35c"/></linearGradient>
  <linearGradient id="earG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.streakShade}"/><stop offset="1" stop-color="#ffb866"/></linearGradient>
  <radialGradient id="blushG"><stop offset="0" stop-color="${C.blush}" stop-opacity=".75"/><stop offset="1" stop-color="${C.blush}" stop-opacity="0"/></radialGradient>
  <radialGradient id="bellG" cx=".35" cy=".3"><stop offset="0" stop-color="#fff3b0"/><stop offset=".5" stop-color="${C.bell}"/><stop offset="1" stop-color="${C.bellShade}"/></radialGradient>
  <clipPath id="eyeClip"><path d="${EYE}"/></clipPath>
  <clipPath id="faceClip"><path d="${FACE}"/></clipPath>
  <clipPath id="bangClip"><path d="${BANGS}"/></clipPath>
  <clipPath id="backClip"><path d="${BACK_HAIR}"/></clipPath>
  <clipPath id="bodyClip"><path d="M285,1090 C285,820 370,705 500,705 C630,705 715,820 715,1090 Z"/></clipPath>
  <pattern id="dots" width="46" height="46" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="7" fill="#fff" opacity=".9"/><circle cx="35" cy="35" r="5" fill="#fff" opacity=".9"/></pattern>
</defs>
${bg ? '<rect width="1000" height="1000" fill="#fff1dc"/><g opacity=".5" fill="#ffd9a8">' + Array.from({ length: 25 }, (_, i) => `<rect x="${(i % 5) * 200 + ((i / 5 | 0) % 2 ? 100 : 0)}" y="${(i / 5 | 0) * 200}" width="100" height="100"/>`).join('') + '</g>' : ''}

<!-- back hair -->
${P(BACK_HAIR, 'url(#backG)')}
<g clip-path="url(#backClip)"><path d="M250,560 Q300,640 290,720 M750,560 Q700,640 710,720 M210,470 Q215,560 180,640 M790,470 Q785,560 820,640" fill="none" stroke="${C.line}" stroke-width="3.5" opacity=".35" stroke-linecap="round"/></g>

<!-- ears -->
${both(P(EAR, 'url(#earG)') + `<path d="${EAR_IN}" fill="${C.earIn}"/><path d="${EAR_FLUFF}" fill="${C.hair}" stroke="${C.line}" stroke-width="4" stroke-linejoin="round"/>`)}

<!-- body -->
<g transform="translate(0,-66)">
${P('M462,620 L462,720 L538,720 L538,620 Z', C.skinShade)}
${P('M285,1090 C285,820 370,705 500,705 C630,705 715,820 715,1090 Z', C.shirt)}
<g clip-path="url(#bodyClip)">
  <path d="M285,1090 C300,880 330,800 380,750 C360,850 360,930 370,1090 Z M715,1090 C700,880 670,800 620,750 C640,850 640,930 630,1090 Z" fill="${C.shirtShade}"/>
  <path d="M500,790 V1090" stroke="${C.line}" stroke-width="3.5" opacity=".5"/>
  <circle cx="500" cy="905" r="9" fill="${C.collar}" stroke="${C.line}" stroke-width="3.5"/><circle cx="500" cy="965" r="9" fill="${C.collar}" stroke="${C.line}" stroke-width="3.5"/>
</g>
${both(P('M500,712 C440,700 385,715 345,760 C390,800 450,800 500,760 Z', C.collar) + '<path d="M368,768 C405,792 452,790 490,762" fill="none" stroke="#fff" stroke-width="5" opacity=".85"/>')}
<!-- bow -->
${both(P('M500,765 C440,720 385,718 352,742 C372,790 372,820 356,862 C410,868 460,838 500,800 Z', C.bow) + `<path d="M500,765 C440,720 385,718 352,742 C372,790 372,820 356,862 C410,868 460,838 500,800 Z" fill="url(#dots)"/><path d="M490,790 C450,822 410,845 368,852" fill="none" stroke="${C.bowShade}" stroke-width="8" opacity=".55" stroke-linecap="round"/>`)}
${P('M470,758 Q500,746 530,758 Q538,782 530,808 Q500,818 470,808 Q462,782 470,758 Z', C.bowShade)}
<!-- bell -->
<circle cx="500" cy="842" r="30" fill="url(#bellG)" stroke="${C.line}" stroke-width="5"/>
<path d="M471,838 H529" stroke="${C.line}" stroke-width="4"/><circle cx="500" cy="852" r="5.5" fill="${C.line}"/><path d="M500,856 V870" stroke="${C.line}" stroke-width="4" stroke-linecap="round"/>

</g>
<!-- face -->
${P(FACE, C.skin)}
<g clip-path="url(#faceClip)">
  <path d="${BANGS}" fill="${C.skinShade}" transform="translate(0,16)" opacity=".8"/>
  <ellipse cx="340" cy="582" rx="62" ry="36" fill="url(#blushG)"/><ellipse cx="660" cy="582" rx="62" ry="36" fill="url(#blushG)"/>
</g>
<path d="M318,586 l10,-14 M338,590 l10,-14 M652,590 l10,-14 M672,586 l10,-14" stroke="#f0787c" stroke-width="3.5" stroke-linecap="round" opacity=".8"/>
${eyes === 'open' ? both(eyeOpen()) + eyeShine(0) + eyeShine(196) : both(eyeClosed)}
${mouth === 'open' ? mouthOpen : mouthClosed}

<!-- front hair -->
${P(BANGS, 'url(#hairG)')}
<g clip-path="url(#bangClip)">
  <path d="${STREAK}" fill="url(#streakG)" stroke="${C.line}" stroke-width="4" stroke-linejoin="round"/>
  <path d="M318,318 Q372,270 440,262 M468,260 Q490,258 512,260" fill="none" stroke="#fff" stroke-width="15" stroke-linecap="round" opacity=".9"/>
  <path d="M556,268 Q600,262 640,284" fill="none" stroke="#ffd9a0" stroke-width="12" stroke-linecap="round" opacity=".9"/>
  <path d="M300,480 Q296,540 304,590 M700,480 Q704,540 696,590 M410,300 Q395,345 400,400 M480,290 Q470,360 482,440" fill="none" stroke="${C.line}" stroke-width="3.5" opacity=".3" stroke-linecap="round"/>
</g>
<path d="${BANGS}" fill="none" stroke="${C.line}" stroke-width="${SW}" stroke-linejoin="round"/>
<!-- brows (drawn over the fringe) -->
<path d="M366,428 Q398,414 432,424 M568,424 Q602,414 634,428" fill="none" stroke="${C.line}" stroke-width="5.5" stroke-linecap="round" opacity=".55"/>
<!-- ahoge -->
<path d="M492,200 C455,120 520,70 565,100 C598,124 580,165 548,158" fill="none" stroke="${C.line}" stroke-width="34" stroke-linecap="round"/>
<path d="M492,200 C455,120 520,70 565,100 C598,124 580,165 548,158" fill="none" stroke="${C.hair}" stroke-width="22" stroke-linecap="round"/>
<path d="M540,96 C570,100 582,128 566,146" fill="none" stroke="${C.streak}" stroke-width="22" stroke-linecap="round"/>
<!-- fish hair clip -->
<g transform="translate(300,400) rotate(-22)">
  ${P('M-34,0 Q-8,-24 24,0 Q-8,24 -34,0 Z M24,0 L46,-18 L42,0 L46,18 Z', C.bow, 'stroke-width="4.5"')}
  <circle cx="-16" cy="-3" r="3.5" fill="${C.line}"/>
</g>
</svg>`;
}

const STATES = {
  idle: { eyes: 'open', mouth: 'closed' }, talk: { eyes: 'open', mouth: 'open' },
  blink: { eyes: 'closed', mouth: 'closed' }, blink_talk: { eyes: 'closed', mouth: 'open' },
};

(async () => {
  const out = process.argv[2] || path.join(__dirname, 'out');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1000, height: 1000 }, deviceScaleFactor: 2 });
  for (const [name, st] of Object.entries(STATES)) {
    fs.writeFileSync(path.join(out, `${name}.svg`), svg(st));
    await page.setContent(`<body style="margin:0;background:transparent">${svg(st)}</body>`);
    await page.screenshot({ path: path.join(out, `${name}.png`), omitBackground: true });
  }
  // preview sheet
  await page.setViewportSize({ width: 1500, height: 1000 });
  const small = Object.keys(STATES).slice(1).map((n) => `<div style="width:290px;height:290px;border-radius:50%;overflow:hidden;border:10px solid #f6953a;background:#fff1dc;margin:10px">${svg(STATES[n]).replace('viewBox="0 0 1000 1000" width="1000" height="1000"', 'viewBox="210 230 580 580" width="290" height="290"')}</div>`).join('');
  await page.setContent(`<body style="margin:0;display:flex;background:#fff1dc"><div style="width:1000px;height:1000px">${svg(STATES.idle, true)}</div><div style="width:500px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#ffe2bd">${small}</div></body>`);
  await page.screenshot({ path: path.join(out, 'preview.png') });
  await browser.close();
  console.log('wrote', fs.readdirSync(out).join(', '));
})();
