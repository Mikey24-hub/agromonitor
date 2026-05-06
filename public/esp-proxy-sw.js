// ✅ Service Worker CORS Proxy para ESP
const CACHE_NAME = 'esp-proxy-v1';

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    
    // ✅ Proxy para /esp-proxy?target=...
    if (url.pathname === '/esp-proxy') {
        const target = decodeURIComponent(url.searchParams.get('target'));
        
        event.respondWith(
            fetch(target, {
                method: event.request.method,
                headers: event.request.headers,
                body: event.request.body,
                mode: 'cors',
                credentials: 'omit'
            }).catch(() => {
                return new Response('ESP Proxy: No response', { status: 503 });
            })
        );
    }
});
