import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  // Archive tooling can unpack CAD and Isaac into public/ for offline use.
  // Only static/ is eligible to be copied into the website.
  publicDir: './static',
  trailingSlash: 'always',
  // Preserve the imported article's recorded-data scripts as authored.
  compressHTML: false,
});
