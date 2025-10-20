module.exports = ({
  transpileDependencies: true,
  devServer: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000', // URL твоего Django-сервера
        changeOrigin: true,
        // logLevel: 'debug', // Полезно для отладки
      },
    },
  }
})
