import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Initialize Capacitor plugins when running in a native shell (Android / iOS).
// In a browser or Electron these imports are no-ops.
async function initNative() {
  const w = window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } };
  if (!w.Capacitor?.isNativePlatform?.()) return;

  const [{ SplashScreen }, { StatusBar, Style }] = await Promise.all([
    import('@capacitor/splash-screen'),
    import('@capacitor/status-bar'),
  ]);

  await StatusBar.setStyle({ style: Style.Dark });
  await StatusBar.setBackgroundColor({ color: '#0d1117' });
  await SplashScreen.hide();
}

initNative().catch(console.error);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
