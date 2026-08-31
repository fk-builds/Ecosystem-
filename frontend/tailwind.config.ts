import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          bg: "#0a0f1a",
          panel: "#0e1526",
          border: "#1c2740",
          accent: "#10b981",
          accentSoft: "#064e3b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
