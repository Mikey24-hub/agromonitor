const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');
const app = express();

// ✅ SIRVE public/ correctamente
app.use('/public', express.static(path.join(__dirname, 'public')));
app.use(express.static(path.join(__dirname, 'static')));

// ✅ Proxy ESP (cualquier IP)
app.use('/esp-proxy', (req, res, next) => {
    const target = req.query.target;
    if (!target) return res.status(400).send('Falta target');
    
    const proxy = createProxyMiddleware({
        target: target,
        changeOrigin: true,
        pathRewrite: { '^/esp-proxy': '' },
        onError: (err, req, res) => {
            res.status(503).json({ error: 'ESP offline' });
        }
    });
    proxy(req, res, next);
});

// ✅ Rutas principales
app.get('/', (req, res) => res.sendFile(path.join(__dirname, 'templates/index_simple.html')));
app.get('/esp_config.html', (req, res) => res.sendFile(path.join(__dirname, 'public/esp_config.html')));

// ✅ Tus rutas existentes (data, csv, etc)
app.get('/data', async (req, res) => {
    // Tu lógica existente
    res.json({ temp: 25.5, humidity: 65, rain: 0 });
});

app.listen(process.env.PORT || 5000, () => {
    console.log('🌱 AgroMonitor corriendo!');
});
