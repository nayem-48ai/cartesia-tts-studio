module.exports = {
  darkMode: 'class',
  content: ['./templates/**/*.html'],
  theme: {
    extend: {
      fontFamily: { sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'] },
      colors: {
        brand: { 50:'#eef2ff',100:'#e0e7ff',200:'#c7d2fe',300:'#a5b4fc',400:'#818cf8',500:'#6366f1',600:'#4f46e5',700:'#4338ca',800:'#3730a3',900:'#312e81' },
        cta: { 50:'#ecfdf5',400:'#34d399',500:'#10b981',600:'#059669',700:'#047857' }
      }
    }
  }
}
