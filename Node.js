// server.js - простой прокси-сервер на Node.js
const express = require('express');
const axios = require('axios');
const HttpsProxyAgent = require('https-proxy-agent');
const cors = require('cors');
const app = express();
const PORT = process.env.PORT || 3000;

// Настройки прокси
const PROXY_URL = 'http://timmycpjj:dGMG8HtDzC@85.209.177.85:59100';

// Добавляем включение TLS без проверки сертификата для обхода проблем с SSL
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
const proxyAgent = new HttpsProxyAgent(PROXY_URL);

app.use(cors());
app.use(express.json());

// Эндпоинт для проксирования запросов к Groq API
app.post('/proxy-to-groq', async (req, res) => {
  try {
    const { apiKey, model, messages, temperature, max_tokens } = req.body;
    
    const response = await axios.post('https://api.groq.com/openai/v1/chat/completions', {
      model,
      messages,
      temperature,
      max_tokens
    }, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      httpsAgent: proxyAgent
    });
    
    res.json(response.data);
  } catch (error) {
    console.error('Ошибка прокси-запроса:', error.message);
    res.status(error.response?.status || 500).json({
      error: error.message,
      details: error.response?.data || {}
    });
  }
});

// Статические файлы (фронтенд)
app.use(express.static('public'));

app.listen(PORT, () => {
  console.log(`Прокси-сервер запущен на порту ${PORT}`);
});

// package.json
/*
{
  "name": "chat-proxy-server",
  "version": "1.0.0",
  "description": "Прокси для Groq API",
  "main": "server.js",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "axios": "^1.6.2",
    "cors": "^2.8.5",
    "express": "^4.18.2",
    "https-proxy-agent": "^7.0.2"
  }
}
*/
