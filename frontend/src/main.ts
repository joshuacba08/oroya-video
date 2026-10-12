import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

bootstrapApplication(App, appConfig).catch((err) => {
  console.error(err);
  // Sin Angular no hay traducciones: mensaje mínimo y bilingüe en lugar de una ventana vacía.
  const message = document.createElement('div');
  message.setAttribute('role', 'alert');
  message.style.cssText =
    'font: 15px system-ui, sans-serif; color: #e5e7eb; background: #0b0d18; padding: 48px; ' +
    'min-height: 100vh; box-sizing: border-box;';
  message.innerHTML =
    '<h1 style="font-size:20px;margin:0 0 12px">Oroya Video no pudo iniciarse</h1>' +
    '<p style="margin:0 0 8px">Cierra la aplicación y vuelve a abrirla. Si sigue fallando, ' +
    'reinstálala desde la página de releases.</p>' +
    '<p style="margin:0;color:#9ca3af">Oroya Video could not start. Restart the app; if it ' +
    'keeps failing, reinstall it from the releases page.</p>';
  document.body.replaceChildren(message);
});
