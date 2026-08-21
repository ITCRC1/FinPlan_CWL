import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        base:      "var(--bg-base)",
        surface:   "var(--bg-surface)",
        elevated:  "var(--bg-elevated)",
        input:     "var(--bg-input)",
        header:    "var(--bg-header)",
        brand:     "var(--brand)",
        positive:  "var(--positive)",
        negative:  "var(--negative)",
        warning:   "var(--warning)",
        neutral:   "var(--neutral)",
        primary:   "var(--text-primary)",
        secondary: "var(--text-secondary)",
        disabled:  "var(--text-disabled)",
        "border-subtle": "var(--border-subtle)",
        "border-medium": "var(--border-medium)",
        "border-focus":  "var(--border-focus)",
      },
      fontFamily: {
        ui:      ["var(--font-ui)"],
        mono:    ["var(--font-mono)"],
      },
      fontSize: {
        "2xs": "11px",
        xs:    "12px",
        sm:    "13px",
        base:  "13px",
        md:    "14px",
        lg:    "16px",
        xl:    "20px",
        "2xl": "24px",
        "3xl": "32px",
      },
    },
  },
  plugins: [],
};
export default config;
