import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
// SIE Frontend Foundation & Core UX Implementation v0.1: the live
// application entry point now mounts the NEW SIE app (src/app/App.tsx),
// not the legacy prototype (src/App.tsx). The legacy file is left
// completely untouched — see docs/FRONTEND_ARCHITECTURE.md.
import App from './app/App.tsx';
import { AppErrorBoundary } from './app/AppErrorBoundary';
import './index.css';

// Safely suppress non-application noise from browser extensions (e.g. MetaMask / web3 injection in iframes)
if (typeof window !== 'undefined') {
  const isExtensionNoise = (msg: string = ''): boolean => {
    const lower = msg.toLowerCase();
    return (
      lower.includes('metamask') ||
      lower.includes('ethereum') ||
      lower.includes('failed to connect to metamask') ||
      lower.includes('chrome-extension://') ||
      lower.includes('moz-extension://') ||
      lower.includes('evm') ||
      lower.includes('solana')
    );
  };

  window.addEventListener('error', (event) => {
    if (isExtensionNoise(event.message || '') || isExtensionNoise(event.filename || '')) {
      event.preventDefault();
      event.stopPropagation();
      return true;
    }
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const msg = typeof reason === 'string' ? reason : (reason?.message || reason?.stack || '');
    if (isExtensionNoise(msg)) {
      event.preventDefault();
      event.stopPropagation();
    }
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>,
);

