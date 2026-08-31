import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { ErrorBoundary } from './components/ErrorBoundary';
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
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);

