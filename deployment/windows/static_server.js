const fs = require('fs');
const http = require('http');
const https = require('https');
const path = require('path');
const { URL } = require('url');

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

const port = Number(argValue('--port', process.env.TECHTRACKER_FRONTEND_PORT || 8080));
const distDir = path.resolve(argValue('--dist', process.env.TECHTRACKER_FRONTEND_DIST || path.join(process.cwd(), 'techtracker_vue', 'dist')));
const backendBase = new URL(argValue('--backend', process.env.TECHTRACKER_BACKEND_URL || 'http://127.0.0.1:8000'));
const normalizedDistDir = distDir.toLowerCase();

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function sendFile(res, filePath) {
  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Not found');
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
    res.end(content);
  });
}

function proxyApi(req, res) {
  const target = new URL(req.url, backendBase);
  const options = {
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port || (target.protocol === 'https:' ? 443 : 80),
    path: `${target.pathname}${target.search}`,
    method: req.method,
    headers: { ...req.headers, host: target.host },
  };

  const transport = target.protocol === 'https:' ? https : http;
  const proxyReq = transport.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
    proxyRes.pipe(res);
  });
  proxyReq.on('error', (err) => {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ detail: `Backend proxy failed: ${err.message}` }));
  });
  req.pipe(proxyReq);
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith('/api/')) {
    proxyApi(req, res);
    return;
  }

  const parsed = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const safePath = path.normalize(decodeURIComponent(parsed.pathname)).replace(/^[/\\]+/, '');
  let filePath = path.resolve(distDir, safePath);
  if (!safePath || safePath === '.' || !path.extname(filePath)) {
    filePath = path.join(distDir, 'index.html');
  }
  const normalizedFilePath = filePath.toLowerCase();
  if (normalizedFilePath !== normalizedDistDir && !normalizedFilePath.startsWith(`${normalizedDistDir}${path.sep}`)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Forbidden');
    return;
  }
  sendFile(res, filePath);
});

server.listen(port, '0.0.0.0', () => {
  console.log(`TechTracker frontend is listening on 0.0.0.0:${port}`);
  console.log(`Serving ${distDir}`);
  console.log(`Proxy /api/ -> ${backendBase.href}`);
});
