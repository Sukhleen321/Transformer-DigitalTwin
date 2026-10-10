/* Opt-in current frontend with explicit current-source API configuration. */
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const [api, port, interval = '4000'] = process.argv.slice(2);
process.env.VITE_API_BASE_URL = api;
process.env.VITE_LIVE_PHYSICS_DEMO_ENABLED = 'true';
process.env.VITE_LIVE_PHYSICS_POLL_INTERVAL_MS = interval;
const root = path.resolve(__dirname, '..');
(async () => {
  const { createServer } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')).href);
  const server = await createServer({ root, configFile: path.join(root, 'vite.config.ts'), server: { host: '127.0.0.1', port: Number(port), strictPort: true } });
  await server.listen();
  console.log(`LIVE SIMULATION frontend http://127.0.0.1:${port}; backend ${api}`);
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await server.close(); process.exit(0); });
})().catch(e => { console.error(e.message); process.exitCode = 1; });
