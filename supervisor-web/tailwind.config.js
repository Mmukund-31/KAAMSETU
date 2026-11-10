/** @type {import('tailwindcss').Config} */
// Design tokens: neutral surfaces, navy ink, teal primary, amber warning, red critical. No gradients.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0f172a", muted: "#475569", faint: "#94a3b8" },
        surface: { DEFAULT: "#ffffff", subtle: "#f8fafc", sunken: "#f1f5f9" },
        line: { DEFAULT: "#e2e8f0", strong: "#cbd5e1" },
        primary: { 50: "#f0fdfa", 100: "#ccfbf1", 600: "#0d9488", 700: "#0f766e", 800: "#115e59" },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "Cascadia Mono", "Consolas", "monospace"],
      },
      boxShadow: { card: "0 1px 2px rgb(15 23 42 / 0.06)" },
    },
  },
  plugins: [],
};
