const v = (n) => `rgb(var(--${n}) / <alpha-value>)`;
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"), surface: v("surface"), ink: v("ink"), muted: v("muted"),
        line: v("line"), kiln: v("kiln"), "kiln-ink": v("kiln-ink"),
        moss: v("moss"), amber: v("amber"), danger: v("danger"),
      },
      fontFamily: {
        display: ["ui-rounded", "'Avenir Next'", "'Trebuchet MS'", "system-ui", "sans-serif"],
        sans: ["system-ui", "-apple-system", "'Segoe UI'", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
