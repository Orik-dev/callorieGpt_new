# import logging
# import base64
# import httpx
# from app.config import settings

# logger = logging.getLogger(__name__)


# async def ai_request(
#     user_id: int,
#     text: str,
#     image_link: str = None
# ) -> tuple[int, str]:
#     """
#     Отправляет запрос к OpenAI API для анализа еды
    
#     Args:
#         user_id: ID пользователя (для логирования)
#         text: Текстовое описание или запрос
#         image_link: URL изображения (опционально)
        
#     Returns:
#         tuple[int, str]: (status_code, response_text)
#     """
#     try:
#         logger.info(f"[GPT API] Request from user {user_id}")
        
#         # Формируем системный промпт
#         system_prompt = """Ты — эксперт по питанию и подсчету калорий. 

# ЗАДАЧА: Анализируй описания блюд или фото еды и возвращай точные данные о калорийности и БЖУ.

# ФОРМАТ ОТВЕТА (СТРОГО JSON):
# {
#   "items": [
#     {
#       "name": "Название блюда",
#       "weight_grams": вес в граммах (число),
#       "calories": калории (число),
#       "protein": белки в граммах (число),
#       "fat": жиры в граммах (число),
#       "carbs": углеводы в граммах (число),
#       "confidence": уверенность 0-1 (число)
#     }
#   ],
#   "notes": "Краткий комментарий или совет (опционально)"
# }

# ПРАВИЛА:
# 1. Если это НЕ еда (например, человек, здание) - верни пустой массив items и notes с объяснением
# 2. Если несколько блюд на фото - раздели их в отдельные элементы массива
# 3. Вес определяй визуально или из описания (стандартные порции)
# 4. Калории считай по формуле: (белки × 4) + (жиры × 9) + (углеводы × 4)
# 5. Будь точным в оценках, используй базы данных о продуктах
# 6. Если есть сомнения в весе - указывай средний размер порции
# 7. В notes давай краткие советы (если есть что сказать)

# ПРИМЕРЫ:

# Запрос: "гречка 200г с курицей 150г"
# Ответ:
# {
#   "items": [
#     {"name": "Гречка отварная", "weight_grams": 200, "calories": 220, "protein": 8, "fat": 2, "carbs": 44, "confidence": 0.95},
#     {"name": "Куриная грудка", "weight_grams": 150, "calories": 248, "protein": 47, "fat": 6, "carbs": 0, "confidence": 0.9}
#   ],
#   "notes": "Отличное сбалансированное блюдо с высоким содержанием белка"
# }

# Запрос: [фото кота]
# Ответ:
# {
#   "items": [],
#   "notes": "На фото изображен кот, а не продукт питания. Отправьте фото еды для анализа."
# }"""

#         # Формируем контент сообщения
#         content = []
        
#         # Добавляем текст
#         content.append({
#             "type": "text",
#             "text": text
#         })
        
#         # Добавляем изображение если есть
#         if image_link:
#             content.append({
#                 "type": "image_url",
#                 "image_url": {
#                     "url": image_link
#                 }
#             })
        
#         # Формируем запрос к OpenAI
#         payload = {
#             "model": settings.openai_default_model,
#             "messages": [
#                 {
#                     "role": "system",
#                     "content": system_prompt
#                 },
#                 {
#                     "role": "user",
#                     "content": content
#                 }
#             ],
#             "temperature": 0.3,
#             "max_tokens": 1500,
#             "response_format": {"type": "json_object"}
#         }
        
#         # Отправляем запрос
#         async with httpx.AsyncClient(timeout=60.0) as client:
#             response = await client.post(
#                 settings.openai_api_url,
#                 headers={
#                     "Authorization": f"Bearer {settings.openai_api_key}",
#                     "Content-Type": "application/json"
#                 },
#                 json=payload
#             )
            
#             if response.status_code != 200:
#                 logger.error(
#                     f"[GPT API] Error {response.status_code}: {response.text}"
#                 )
#                 return response.status_code, ""
            
#             data = response.json()
            
#             # Извлекаем ответ
#             if "choices" not in data or len(data["choices"]) == 0:
#                 logger.error("[GPT API] No choices in response")
#                 return 500, ""
            
#             message_content = data["choices"][0]["message"]["content"]
            
#             logger.info(
#                 f"[GPT API] Success for user {user_id}, "
#                 f"tokens: {data.get('usage', {}).get('total_tokens', 0)}"
#             )
            
#             return 200, message_content
            
#     except httpx.TimeoutException:
#         logger.error(f"[GPT API] Timeout for user {user_id}")
#         return 504, ""
#     except Exception as e:
#         logger.exception(f"[GPT API] Unexpected error for user {user_id}: {e}")
#         return 500, ""

import logging
import base64
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def ai_request(
    user_id: int,
    text: str,
    image_link: str = None
) -> tuple[int, str]:
    """
    Отправляет запрос к OpenAI API для анализа еды
    
    Args:
        user_id: ID пользователя (для логирования)
        text: Текстовое описание или запрос
        image_link: URL изображения (опционально)
        
    Returns:
        tuple[int, str]: (status_code, response_text)
    """
    try:
        logger.info(f"[GPT API] Request from user {user_id}")
        
        # Формируем системный промпт
        system_prompt = """Ты — эксперт по питанию и подсчету калорий. 

ЗАДАЧА: Анализируй описания блюд или фото еды и возвращай точные данные о калорийности и БЖУ.

ФОРМАТ ОТВЕТА (СТРОГО JSON):
{
  "items": [
    {
      "name": "Название блюда",
      "weight_grams": вес в граммах (число),
      "calories": калории (число),
      "protein": белки в граммах (число),
      "fat": жиры в граммах (число),
      "carbs": углеводы в граммах (число),
      "confidence": уверенность 0-1 (число)
    }
  ],
  "notes": "Краткий комментарий или совет (опционально)"
}

ПРАВИЛА:
1. Если это НЕ еда (например, человек, здание) - верни пустой массив items и notes с объяснением
2. Если несколько блюд на фото - раздели их в отдельные элементы массива
3. Вес определяй визуально или из описания (стандартные порции)
4. Калории считай по формуле: (белки × 4) + (жиры × 9) + (углеводы × 4)
5. Будь точным в оценках, используй базы данных о продуктах
6. Если есть сомнения в весе - указывай средний размер порции
7. В notes давай краткие советы (если есть что сказать)

ПРИМЕРЫ:

Запрос: "гречка 200г с курицей 150г"
Ответ:
{
  "items": [
    {"name": "Гречка отварная", "weight_grams": 200, "calories": 220, "protein": 8, "fat": 2, "carbs": 44, "confidence": 0.95},
    {"name": "Куриная грудка", "weight_grams": 150, "calories": 248, "protein": 47, "fat": 6, "carbs": 0, "confidence": 0.9}
  ],
  "notes": "Отличное сбалансированное блюдо с высоким содержанием белка"
}

Запрос: [фото кота]
Ответ:
{
  "items": [],
  "notes": "На фото изображен кот, а не продукт питания. Отправьте фото еды для анализа."
}"""

        # Формируем контент сообщения
        content = []
        
        # Добавляем текст
        content.append({
            "type": "text",
            "text": text
        })
        
        # Добавляем изображение если есть
        if image_link:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": image_link
                }
            })
        
        # Формируем запрос к OpenAI
        payload = {
            "model": settings.openai_default_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            "temperature": 0.3,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }
        
        # Отправляем запрос
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                settings.openai_api_url,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(
                    f"[GPT API] Error {response.status_code}: {response.text}"
                )
                return response.status_code, ""
            
            data = response.json()
            
            # Извлекаем ответ
            if "choices" not in data or len(data["choices"]) == 0:
                logger.error("[GPT API] No choices in response")
                return 500, ""
            
            message_content = data["choices"][0]["message"]["content"]
            
            logger.info(
                f"[GPT API] Success for user {user_id}, "
                f"tokens: {data.get('usage', {}).get('total_tokens', 0)}"
            )
            
            return 200, message_content
            
    except httpx.TimeoutException:
        logger.error(f"[GPT API] Timeout for user {user_id}")
        return 504, ""
    except Exception as e:
        logger.exception(f"[GPT API] Unexpected error for user {user_id}: {e}")
        return 500, ""