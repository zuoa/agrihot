/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        leaf: {
          50: '#f2f9f0',
          100: '#e0f1db',
          200: '#c2e3ba',
          300: '#96ce8b',
          400: '#66b35c',
          500: '#44963c',
          600: '#327a2d',
          700: '#296026',
          800: '#234e22',
          900: '#1e401e',
          950: '#0c230d',
        },
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
