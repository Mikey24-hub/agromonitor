const CACHE_NAME = 'agromonitor-v5.2-v1';
const urlsToCache = [
  '/',
  '/index_simple.html',
  '/csv_view.html',
  '/data',
  '/data_full',
  '/status'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
