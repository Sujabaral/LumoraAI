const CACHE_NAME = 'lumora-cache-v1';
const urlsToCache = [
  '/home',
  '/static/images/logo.png'
  
];

// Install event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache))
  );
  console.log('✅ LUMORA Service Worker installed');
});

// Fetch event
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
