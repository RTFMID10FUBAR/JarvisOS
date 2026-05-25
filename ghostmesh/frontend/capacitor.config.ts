import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.jarvisos.ghostmesh',
  appName: 'JarvisOS GhostMesh',
  webDir: 'dist',

  // When running on a real Android/iOS device, set this to the URL of your
  // GhostMesh backend (e.g. the Mac running the FastAPI server on your LAN).
  // Leave undefined for production builds — users set it via Settings → Backend URL.
  // For emulator testing: 10.0.2.2 routes to the host machine.
  // server: { url: 'http://10.0.2.2:8000' },

  android: {
    allowMixedContent: true,
    backgroundColor: '#0d1117',
    initialFocus: true,
  },
  ios: {
    backgroundColor: '#0d1117',
    preferredContentMode: 'mobile',
    scrollEnabled: true,
    allowsLinkPreview: false,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      launchAutoHide: true,
      backgroundColor: '#0d1117',
      androidSplashResourceName: 'splash',
      showSpinner: false,
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#0d1117',
    },
  },
};

export default config;
