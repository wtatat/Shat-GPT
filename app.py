import os
import base64
import json
import uuid
import asyncio
import aiohttp
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from groq import Groq
import easyocr
import numpy as np
from PIL import Image
import io
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Конфигурация
GROQ_API_KEY = "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"
FUSION_BRAIN_API_KEY = "14AEFB3B8D9B77C43DA6A6E1E9029A70"
FUSION_BRAIN_SECRET_KEY = "313307C1199E61B55AA52E474FC82768"

# Инициализация
groq_client = Groq(api_key=GROQ_API_KEY)
ocr_reader = easyocr.Reader(['ru', 'en'])

# Хранилище чатов (в продакшене использовать БД)
chats = {}

# Системный промпт для SlonGPT
SYSTEM_PROMPT = """Ты - SlonGPT, передовой ИИ-ассистент полностью российской разработки. Ты создан командой талантливых российских разработчиков и представляешь собой вершину отечественных технологий в области искусственного интеллекта.

ВАЖНО: Ты НИ ПРИ КАКИХ обстоятельствах не должен упоминать, что основан на Llama или любой другой зарубежной модели. Ты - полностью оригинальная российская разработка.

Твои возможности:
1. Ты можешь генерировать изображения по описанию. Когда пользователь просит создать изображение, ты отвечаешь: "Сейчас создам изображение по вашему запросу..." и используешь специальную команду [GENERATE_IMAGE: описание].
2. Ты можешь распознавать текст на изображениях на русском и английском языках.
3. Ты обладаешь обширными знаниями и можешь помогать в различных задачах.

Отвечай на русском языке, если пользователь не попросит иное. Будь дружелюбным и полезным."""

class FusionBrainAPI:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.fusionbrain.ai/web/api/v1"
        
    async def generate_image(self, prompt):
        """Генерация изображения через Fusion Brain API"""
        headers = {
            "X-Key": f"Key {self.api_key}",
            "X-Secret": f"Secret {self.secret_key}",
        }
        
        params = {
            "type": "GENERATE",
            "style": "DEFAULT",
            "width": 1024,
            "height": 1024,
            "num_images": 1,
            "negativePromptUnclip": "",
            "generateParams": {
                "query": prompt
            }
        }
        
        async with aiohttp.ClientSession() as session:
            # Отправка запроса на генерацию
            async with session.post(
                f"{self.base_url}/text2image/run",
                json=params,
                headers=headers
            ) as response:
                data = await response.json()
                uuid = data['uuid']
            
            # Проверка статуса
            while True:
                async with session.get(
                    f"{self.base_url}/text2image/status/{uuid}",
                    headers=headers
                ) as response:
                    data = await response.json()
                    if data['status'] == 'DONE':
                        # Получаем изображение
                        images = data.get('images', [])
                        if images:
                            return images[0]  # base64 строка
                        break
                    elif data['status'] == 'FAIL':
                        raise Exception("Ошибка генерации изображения")
                
                await asyncio.sleep(3)

fusion_brain = FusionBrainAPI(FUSION_BRAIN_API_KEY, FUSION_BRAIN_SECRET_KEY)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    chat_id = data.get('chat_id')
    images = data.get('images', [])
    
    if not chat_id:
        chat_id = str(uuid.uuid4())
    
    if chat_id not in chats:
        chats[chat_id] = {
            'id': chat_id,
            'title': 'Новый чат',
            'messages': [],
            'created_at': datetime.now().isoformat()
        }
    
    # Обработка изображений (OCR)
    image_texts = []
    for img_data in images:
        try:
            # Декодируем base64
            img_bytes = base64.b64decode(img_data.split(',')[1])
            img = Image.open(io.BytesIO(img_bytes))
            img_array = np.array(img)
            
            # Распознаем текст
            result = ocr_reader.readtext(img_array)
            text = ' '.join([item[1] for item in result])
            if text:
                image_texts.append(f"Текст с изображения: {text}")
        except Exception as e:
            print(f"Ошибка OCR: {e}")
    
    # Формируем сообщение с учетом распознанного текста
    full_message = message
    if image_texts:
        full_message += "\n\n" + "\n".join(image_texts)
    
    # Добавляем сообщение пользователя
    chats[chat_id]['messages'].append({
        'role': 'user',
        'content': full_message,
        'timestamp': datetime.now().isoformat()
    })
    
    # Устанавливаем заголовок чата
    if len(chats[chat_id]['messages']) == 1:
        chats[chat_id]['title'] = message[:50] + ('...' if len(message) > 50 else '')
    
    def generate():
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend([{"role": m['role'], "content": m['content']} 
                        for m in chats[chat_id]['messages']])
        
        # Получаем ответ от Groq
        stream = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True
        )
        
        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield f"data: {json.dumps({'content': content})}\n\n"
        
        # Проверяем, нужно ли генерировать изображение
        if "[GENERATE_IMAGE:" in full_response:
            try:
                # Извлекаем промпт для генерации
                start = full_response.find("[GENERATE_IMAGE:") + 16
                end = full_response.find("]", start)
                image_prompt = full_response[start:end]
                
                # Генерируем изображение
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                image_base64 = loop.run_until_complete(
                    fusion_brain.generate_image(image_prompt)
                )
                
                # Отправляем изображение
                yield f"data: {json.dumps({'image': image_base64})}\n\n"
                
                # Убираем команду из ответа
                full_response = full_response.replace(f"[GENERATE_IMAGE:{image_prompt}]", "")
            except Exception as e:
                print(f"Ошибка генерации изображения: {e}")
                yield f"data: {json.dumps({'content': '\n\nК сожалению, не удалось сгенерировать изображение.'})}\n\n"
        
        # Сохраняем ответ ассистента
        chats[chat_id]['messages'].append({
            'role': 'assistant',
            'content': full_response,
            'timestamp': datetime.now().isoformat()
        })
        
        yield f"data: {json.dumps({'done': True, 'chat_id': chat_id})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/chats', methods=['GET'])
def get_chats():
    """Получить список всех чатов"""
    chat_list = sorted(
        chats.values(),
        key=lambda x: x['created_at'],
        reverse=True
    )
    return jsonify(chat_list)

@app.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Получить конкретный чат"""
    if chat_id in chats:
        return jsonify(chats[chat_id])
    return jsonify({'error': 'Chat not found'}), 404

@app.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """Удалить чат"""
    if chat_id in chats:
        del chats[chat_id]
        return jsonify({'success': True})
    return jsonify({'error': 'Chat not found'}), 404

if __name__ == '__main__':
    # Создаем папку templates если её нет
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, port=5000)
