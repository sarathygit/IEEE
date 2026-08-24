import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Port 5173 is whitelisted in the switch's CORS config (UpiPaymentController).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
});
