const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 3000;

// ✅ Proxy dinámico para ESP (cualquier IP)
app.use('/esp-proxy', (req, res, next) => {
    const targetUrl = req.query.target;
    
    if (!targetUrl || !targetUrl.startsWith('http://')) {
        return res.status(400).json({ error: 'URL target inválida' });
    }
    
    const proxy = createProxyMiddleware({
        target: targetUrl,
        changeOrigin: true,
        pathRewrite: {
            '^/esp-proxy': '',  // Quita /esp-proxy
            [`^/esp-proxy?target=${encodeURIComponent(targetUrl)}`]: ''
        },
        onProxyReq: (proxyReq, req) => {
            // Copia headers y body
            proxyReq.setHeader('Content-Type', 'application/x-www-form-urlencoded');
        },
        onError: (err, req, res) => {
            res.status(503).json({ error: 'ESP no responde', details: err.message });
        }
    });
    
    return proxy(req, res, next);
});

// ✅ Servir archivos estáticos
app.use(express.static(path.join(__dirname, 'public')));

// ✅ Ruta principal
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'esp_config.html'));
});

// ✅ Health check
app.get('/health', (req, res) => {
    res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
    console.log(`🚀 AgroMonitor ESP Config en puerto ${PORT}`);
    console.log(`📱 https://tu-app.onrender.com/esp_config.html`);
});
