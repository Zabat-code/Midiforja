import { defineConfig } from "vite";

// Fresh dev port (per project convention: never reuse an app's own port).
export default defineConfig({
  server: {
    port: 5174,
    strictPort: false,
  },
});
