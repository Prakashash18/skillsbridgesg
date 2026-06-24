import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Canvas + surfaces
        canvas: "#f6f8fb",
        surface: "#ffffff",
        subtle: "#f4f7fa",
        // Text
        ink: "#0d1b2a",
        body: "#3f4a5a",
        muted: "#6b7689",
        faint: "#9aa4b4",
        // Hairlines
        line: "#e7ecf2",
        lineStrong: "#d6dde7",
        // Brand — SkillsFuture teal
        brand: "#0c8079",
        brandStrong: "#0a605c",
        brandSoft: "#e9f7f5",
        brandSofter: "#f4fbfa",
        brandRing: "#16b8aa",
        // SkillsFuture dark petrol (portal header) + coral CTA accent
        petrol: "#0a474c",
        petrolDeep: "#073338",
        coral: "#ef5b45",
        coralStrong: "#d8412c",
        coralSoft: "#fdeee9",
        // Semantic
        positive: "#0c8079",
        warn: "#b45309",
        warnSoft: "#fef3e2",
        danger: "#be123c",
        dangerSoft: "#fff1f3",
        violet: "#6d5ce7",
        violetSoft: "#f0eefe",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
        "3xl": "1.5rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.04), 0 6px 20px rgba(16,24,40,0.05)",
        lift: "0 2px 4px rgba(16,24,40,0.04), 0 14px 34px rgba(16,24,40,0.10)",
        ring: "0 0 0 4px rgba(20,184,166,0.14)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
