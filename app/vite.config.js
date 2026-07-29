import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// Static build only. Served from /v2/ by the EXISTING dashboard-server.py - no dev server, no new port.
export default defineConfig({
  plugins: [svelte()],
  base: '/v2/',
  build: {
    outDir: '../releases/.build-tmp',
    emptyOutDir: true,
    assetsInlineLimit: 0,        // keep assets as real files so a release hash covers every byte we serve
    sourcemap: false,
    target: 'es2022',
    modulePreload: {
      // Vite's modulePreload polyfill is an INLINE <script>, which strict CSP (script-src 'self', no
      // 'unsafe-inline') correctly refuses to run. Disabling it keeps the bundle CSP-pure. Every browser this
      // page targets (the phone + desktop Chrome/Safari) supports modulepreload natively.
      polyfill: false
    }
  }
});
