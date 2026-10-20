/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: '#0c0e12',
          subtle: '#12151c',
          card: '#161922',
          hover: '#1c202b',
        },
        border: {
          subtle: '#222733',
          strong: '#303747',
        },
        accent: {
          DEFAULT: '#c6f135', // Acid Lime
          hover: '#b5e028',
          subtle: 'rgba(198, 241, 53, 0.12)',
          muted: '#8cb020',
        },
        content: {
          primary: '#f4f5f8',
          secondary: '#9ca3af',
          muted: '#6b7280',
          disabled: '#4b5563',
        },
        status: {
          success: '#10b981',
          warning: '#f59e0b',
          error: '#ef4444',
          info: '#3b82f6',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'Courier New', 'monospace'],
      },
      boxShadow: {
        'subtle': '0 1px 3px 0 rgba(0, 0, 0, 0.3), 0 1px 2px -1px rgba(0, 0, 0, 0.3)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.4)',
      }
    },
  },
  plugins: [],
}
