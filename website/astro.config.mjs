import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  trailingSlash: 'always',
  // Preserve the imported article's recorded-data scripts as authored.
  compressHTML: false,
});
