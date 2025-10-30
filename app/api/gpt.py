import json
import pickle
import httpx
from app.config import settings
from app.db.redis_client import redis

OPENAI_PROMPT = """Ты — персональный ассистент по питанию.
Я буду присылать тебе описания своей еды или фотографии блюд, 
а твоя задача — определять название продукта, его вес и рассчитывать количество калорий, белков, жиров и углеводов. Общайся БЕЗ MARKDOWN.
Пожалуйста, предоставляй ответы строго в следующем формате КАК БУДТО В JSON НАСТОЛЬКО СТРОГО ПИШИ ТОЛЬКО ТО ЧТО С ►:

► {Номер}. {Название продукта}: (тут подсчитываешь все с продукта)
   - Вес: {Вес} г
   - БЖУ: {Белки} г белка • {Жиры} г жиров • {Углеводы} г углеводов
   - Калории: {Калории} ккал

► Итого за день: (тут вводишь сколько всего калорий и т.д. из всех продуктов старых и новых)

► Рекомендации: (пишешь Персональные рекомендации).

► Если есть ошибка, просто надиктуйте мне голосовым, и я исправлю.

Всегда придерживайся этого стандарта ответа, даже если информация не полная, например, человек написал кофе — ты даёшь НЕ РЕЦЕПТ, а калораж и т.д., или требуется сделать предположение на основе изображения. Старайся всегда определить блюдо по фотографии! Даже если не уверен, пиши свои предположения. (Никогда не пиши, что не можешь определить блюдо по фотографии)."""

REDIS_KEY = "gpt:ctx:{user_id}"

async def ai_request(user_id: int, model="gpt-4o", text: str = None, image_link: str = None) -> tuple[int, str]:
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            if not text and not image_link:
                return 400, ""

            # Загрузка контекста
            redis_key = REDIS_KEY.format(user_id=user_id)
            raw = await redis.get(redis_key)
            try:
                context = pickle.loads(raw) if raw else []
            except:
                context = []


            if not context:
                context.append({'role': 'system', 'content': OPENAI_PROMPT})

            user_content = []
            if text:
                user_content.append({"type": "text", "text": text})
            if image_link:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_link, "detail": "auto"}
                })

            context.append({'role': 'user', 'content': user_content})

            payload = {"model": model, "messages": context}
            headers = {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json"
            }

            response = await client.post(settings.openai_api_url, headers=headers, json=payload)
            if response.status_code != 200:
                return 400, ""

            reply = response.json()["choices"][0]["message"]["content"]
            context.append({"role": "assistant", "content": reply})

            await redis.set(redis_key, pickle.dumps(context), ex=86400)

            return 200, reply

    except Exception as e:
        print(f"[!!] ai_request: {e}")
        return 400, ""
