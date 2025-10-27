const { defineConfig } = require('@vue/cli-service')
module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000', // URL твоего Django-сервера
        changeOrigin: true,
        // logLevel: 'debug', // Полезно для отладки
      },
      '/admin': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // logLevel: 'debug',
      },
    },    
  }
})
