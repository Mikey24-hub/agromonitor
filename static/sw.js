const CACHE_NAME = 'mikey24hub-v1';
const urlsToCache = [
  '/',
  '/static/manifest.json',
  '/static/seedling.png',
  '/static/seedling.png'
];

self.addEventListener('install', event => {
  console.log('🔧 SW INSTALANDO...');
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('activate', event => {
  console.log('✅ SW ACTIVO');
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => 
      response || fetch(event.request)
    )
  );
});
