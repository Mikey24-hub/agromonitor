if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(() => console.log('✅ PWA Service Worker activo'))
    .catch(err => console.log('❌ SW error:', err));
  
  // Botón instalar
  window.addEventListener('beforeinstallprompt', (e) => {
    e.prompt();
    console.log('📱 ¡Instalar app disponible!');
  });
}
