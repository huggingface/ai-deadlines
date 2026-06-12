
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import yaml from "@modyfi/vite-plugin-yaml";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    // Use 5173 locally to avoid conflicting with Cursor's port-forward on 8080 (HF Space app_port).
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
  },
  plugins: [
    react(),
    mode === 'development' &&
    componentTagger(),
    yaml({
      include: 'src/data/**/*.yml'
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
