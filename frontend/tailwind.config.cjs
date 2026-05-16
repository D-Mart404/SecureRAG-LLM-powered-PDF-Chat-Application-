/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx,html}',
  ],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: '#F5F3F0',
          soft: '#FAFAF8',
          muted: '#F0EEEB',
        },
        ink: {
          DEFAULT: '#1A1A1A',
          soft: '#2D2D2D',
          muted: '#4A4A4A',
          text: '#333333',
        },
        accent: {
          DEFAULT: '#FF7A3D',
          soft: '#FFB399',
          strong: '#E55100',
        },
        border: '#E5E0DA',
        success: '#10B981',
        danger: '#EF4444',
        warning: '#F59E0B',
        info: '#3B82F6',
      },
    },
  },
  plugins: [],
};
