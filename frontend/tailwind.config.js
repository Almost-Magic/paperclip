export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'bg-dark': '#0A0E14',
        'bg-card': '#131820',
        'accent': '#C9944A',
        'text-primary': '#E6EDF3',
        'text-muted': '#8B949E',
      },
      fontFamily: {
        'display': ['Lora', 'serif'],
        'ui': ['Inter', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'DEFAULT': '8px',
      },
    },
  },
  plugins: [],
}
