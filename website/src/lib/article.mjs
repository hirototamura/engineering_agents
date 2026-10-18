const files = { ja: 'index.ja.html', en: 'index.html' };
const reading = {
  ja: {
    other: 'en', otherPath: '/en/',
    label: 'Read this article in English',
    description: '自立Cubeを題材に、MJX探索、マルチエージェント設計、RW配置の修正を図と記録再生でたどる研究ノート。',
  },
  en: {
    other: 'ja', otherPath: '/',
    label: 'この記事を日本語で読む',
    description: 'A research notebook on MJX exploration, multi-agent engineering and reaction-wheel placement, with recorded balancing-cube replay.',
  },
};

export function renderArticle(language, input) {
  const settings = reading[language];
  if (!settings) throw new Error(`Unsupported article language: ${language}`);
  const boundary = input.indexOf('<script id="research-evidence"');
  if (boundary < 0) throw new Error('Missing embedded article evidence');
  // Edit only document metadata/navigation. Preserve all measured data and
  // interactive code byte for byte after the embedded-evidence boundary.
  let prefix = input.slice(0, boundary);
  const suffix = input.slice(boundary);
  const otherFile = files[settings.other];
  const linkPattern = new RegExp(`<a href="${otherFile.replaceAll('.', '\\.')}" lang="${language}">`);
  if (!linkPattern.test(prefix)) throw new Error('Expected exactly one language link');
  prefix = prefix.replace(linkPattern,
    `<a href="${settings.otherPath}" lang="${settings.other}" hreflang="${settings.other}" aria-label="${settings.label}" data-language-switch>`);
  prefix = prefix.replace(/<meta name="description" content="[^"]*">/,
    `<meta name="description" content="${settings.description}">`);
  prefix = prefix.replace('</head>', [
    '<link rel="alternate" hreflang="ja" href="/">',
    '<link rel="alternate" hreflang="en" href="/en/">',
    '<link rel="alternate" hreflang="x-default" href="/">',
    '</head>',
  ].join('\n'));
  return prefix + suffix;
}
