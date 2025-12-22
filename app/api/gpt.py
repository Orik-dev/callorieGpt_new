# # app/api/gpt.py
# import logging
# import asyncio
# import httpx
# from typing import Optional, Tuple
# from app.config import settings

# logger = logging.getLogger(__name__)

# # Retry настройки
# MAX_RETRIES = 3
# RETRY_DELAYS = [1, 2, 4]  # Exponential backoff


# # Универсальный промпт для определения intent
# SYSTEM_PROMPT = """Ты — эксперт по питанию. Анализируй сообщения пользователя и определяй что он хочет.

# ТИПЫ НАМЕРЕНИЙ (intent):
# - "add" — добавить еду в рацион (ПО УМОЛЧАНИЮ для фото и описания еды)
# - "calculate" — только посчитать калории, НЕ добавлять
# - "edit" — изменить последний прием пищи
# - "delete" — удалить что-то из рациона
# - "add_previous" — добавить то, что только что рассчитывали
# - "unknown" — непонятно что хочет пользователь

# ВАЖНО - КОГДА ADD (добавлять):
# - Фото еды → ВСЕГДА "add" (если нет явного вопроса про калории)
# - "съел...", "ел...", "на завтрак/обед/ужин..." → "add"
# - "перекусил...", "выпил..." → "add"
# - Просто название еды без вопроса → "add"

# КОГДА CALCULATE (только посчитать, НЕ добавлять):
# - Явный вопрос: "сколько калорий в...?", "какая калорийность...?"
# - "а если съесть...?", "что если...?", "гипотетически..."
# - "посчитай", "КБЖУ чего-то" (без контекста что съел)

# КОГДА ADD_PREVIOUS:
# - "добавь это", "добавь в рацион", "запиши это"
# - "добавь что рассчитал", "сохрани это"
# - После расчета пользователь хочет добавить

# КОГДА DELETE:
# - "убери", "удали", "отмени", "не ел", "ошибся"
# - "последнее убери", "забудь про..."

# КОГДА EDIT:
# - "исправь", "измени", "на самом деле было...", "там меньше/больше"

# ФОРМАТ ОТВЕТА (строго JSON):
# {
#   "intent": "add|calculate|edit|delete|add_previous|unknown",
#   "items": [
#     {
#       "name": "Название блюда",
#       "weight_grams": число,
#       "calories": число,
#       "protein": число,
#       "fat": число,
#       "carbs": число,
#       "confidence": 0-1
#     }
#   ],
#   "edit_instruction": "что изменить (только для edit)",
#   "delete_target": "что удалить: last/all/название (только для delete)",
#   "notes": "комментарий"
# }

# ПРАВИЛА:
# 1. ФОТО ЕДЫ = "add" по умолчанию (если нет явного вопроса)
# 2. Если это НЕ еда — intent="unknown", items=[], notes с объяснением
# 3. Если несколько блюд — несколько элементов в items
# 4. Калории = (белки × 4) + (жиры × 9) + (углеводы × 4)
# 5. При сомнениях в весе — стандартная порция
# 6. Для edit/delete/add_previous items может быть пустым

# ПРИМЕРЫ:

# [ФОТО ЕДЫ] → intent="add", items=[все блюда с фото]
# [ФОТО ЕДЫ] + "сколько тут калорий?" → intent="calculate"
# "гречка 200г с курицей" → intent="add", items=[{гречка}, {курица}]
# "съел яблоко" → intent="add"
# "сколько калорий в пицце?" → intent="calculate"
# "добавь это в рацион" → intent="add_previous"
# "запиши что рассчитал" → intent="add_previous"
# "убери последнее" → intent="delete", delete_target="last"
# "там было 150г, не 200" → intent="edit"
# """


# async def ai_request(
#     user_id: int,
#     text: str,
#     image_link: str = None,
#     context: str = None
# ) -> Tuple[int, str]:
#     """
#     Отправляет запрос к OpenAI API с retry
    
#     Args:
#         user_id: ID пользователя
#         text: Текст запроса
#         image_link: URL изображения (опционально)
#         context: Контекст (последние приемы пищи)
        
#     Returns:
#         (status_code, response_text)
#     """
    
#     # Формируем сообщение пользователя
#     user_message = text
#     if context:
#         user_message = f"КОНТЕКСТ (последние приемы пищи сегодня):\n{context}\n\nЗАПРОС ПОЛЬЗОВАТЕЛЯ: {text}"
    
#     # Формируем контент
#     content = [{"type": "text", "text": user_message}]
    
#     if image_link:
#         content.append({
#             "type": "image_url",
#             "image_url": {"url": image_link}
#         })
    
#     payload = {
#         "model": settings.openai_default_model,
#         "messages": [
#             {"role": "system", "content": SYSTEM_PROMPT},
#             {"role": "user", "content": content}
#         ],
#         "temperature": 0.3,
#         "max_tokens": 1500,
#         "response_format": {"type": "json_object"}
#     }
    
#     last_error = None
    
#     for attempt in range(MAX_RETRIES):
#         try:
#             logger.info(f"[GPT API] Request for user {user_id} (attempt {attempt + 1})")
            
#             async with httpx.AsyncClient(timeout=60.0) as client:
#                 response = await client.post(
#                     settings.openai_api_url,
#                     headers={
#                         "Authorization": f"Bearer {settings.openai_api_key}",
#                         "Content-Type": "application/json"
#                     },
#                     json=payload
#                 )
                
#                 # Успешный ответ
#                 if response.status_code == 200:
#                     data = response.json()
#                     if "choices" in data and len(data["choices"]) > 0:
#                         content = data["choices"][0]["message"]["content"]
#                         tokens = data.get("usage", {}).get("total_tokens", 0)
#                         logger.info(f"[GPT API] Success for user {user_id}, tokens: {tokens}")
#                         return 200, content
#                     else:
#                         logger.error("[GPT API] No choices in response")
#                         return 500, ""
                
#                 # Rate limit - ждём и повторяем
#                 if response.status_code == 429:
#                     error_data = response.json()
#                     error_msg = error_data.get("error", {}).get("message", "")
                    
#                     # Если это quota exceeded (нет денег) - не ретраим
#                     if "quota" in error_msg.lower():
#                         logger.error(f"[GPT API] Quota exceeded for user {user_id}")
#                         return 429, "QUOTA_EXCEEDED"
                    
#                     # Rate limit - ждём
#                     delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
#                     logger.warning(f"[GPT API] Rate limited, waiting {delay}s")
#                     await asyncio.sleep(delay)
#                     continue
                
#                 # Другие ошибки
#                 logger.error(f"[GPT API] Error {response.status_code}: {response.text[:500]}")
#                 last_error = response.status_code
                
#                 if attempt < MAX_RETRIES - 1:
#                     await asyncio.sleep(RETRY_DELAYS[attempt])
                    
#         except httpx.TimeoutException:
#             logger.error(f"[GPT API] Timeout for user {user_id}")
#             last_error = 504
#             if attempt < MAX_RETRIES - 1:
#                 await asyncio.sleep(RETRY_DELAYS[attempt])
                
#         except Exception as e:
#             logger.exception(f"[GPT API] Unexpected error: {e}")
#             last_error = 500
#             if attempt < MAX_RETRIES - 1:
#                 await asyncio.sleep(RETRY_DELAYS[attempt])
    
#     return last_error or 500, ""

# app/api/gpt.py
import logging
import asyncio
import httpx
from typing import Tuple
from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

SYSTEM_PROMPT = """Ты — эксперт по питанию. Анализируй сообщения пользователя и определяй что он хочет.

ТИПЫ НАМЕРЕНИЙ (intent):
- "add" — добавить еду в рацион (ПО УМОЛЧАНИЮ для фото и описания еды)
- "calculate" — только посчитать калории, НЕ добавлять
- "edit" — изменить последний прием пищи
- "delete" — удалить что-то из рациона
- "add_previous" — добавить то, что только что рассчитывали
- "unknown" — непонятно что хочет пользователь

КОГДА ADD (по умолчанию):
- Фото еды → ВСЕГДА "add" (если нет явного вопроса)
- "съел...", "ел...", "на завтрак/обед/ужин..." → "add"
- Просто название еды → "add"

КОГДА CALCULATE (только посчитать):
- Явный вопрос: "сколько калорий в...?", "какая калорийность?"
- "посчитай КБЖУ", "а если съесть...?"

КОГДА DELETE:
- "убери", "удали", "отмени", "не ел"
- delete_target: "last" / "all" / название

КОГДА EDIT:
- "там было 150г, не 200", "исправь"

ФОРМАТ ОТВЕТА (строго JSON):
{
  "intent": "add|calculate|edit|delete|add_previous|unknown",
  "items": [
    {
      "name": "Название",
      "weight_grams": число,
      "calories": число,
      "protein": число,
      "fat": число,
      "carbs": число
    }
  ],
  "delete_target": "last|all|название (для delete)",
  "notes": "комментарий"
}

ВАЖНО:
- Фото еды = "add" по умолчанию
- Калории = Б×4 + Ж×9 + У×4
- Несколько блюд = несколько items
"""


async def ai_request(
    user_id: int,
    text: str,
    image_link: str = None,
    context: str = None
) -> Tuple[int, str]:
    """Отправляет запрос к OpenAI API"""
    
    user_message = text
    if context:
        user_message = f"КОНТЕКСТ:\n{context}\n\nЗАПРОС: {text}"
    
    content = [{"type": "text", "text": user_message}]
    
    if image_link:
        content.append({
            "type": "image_url",
            "image_url": {"url": image_link, "detail": "low"}
        })
    
    payload = {
        "model": settings.openai_default_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"}
    }
    
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"[GPT API] Request for user {user_id} (attempt {attempt + 1})")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    settings.openai_api_url,
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "choices" in data and len(data["choices"]) > 0:
                        message = data["choices"][0]["message"]
                        result = message.get("content")
                        
                        # Проверка на None/refusal
                        if result is None:
                            refusal = message.get("refusal")
                            finish_reason = data["choices"][0].get("finish_reason")
                            logger.error(
                                f"[GPT API] Content is None! "
                                f"refusal={refusal}, finish_reason={finish_reason}, "
                                f"message={message}"
                            )
                            # Попробуем ещё раз
                            if attempt < MAX_RETRIES - 1:
                                await asyncio.sleep(RETRY_DELAYS[attempt])
                                continue
                            return 500, ""
                        
                        tokens = data.get("usage", {}).get("total_tokens", 0)
                        logger.info(f"[GPT API] Success for user {user_id}, tokens: {tokens}")
                        return 200, result
                    else:
                        logger.error(f"[GPT API] No choices: {data}")
                        return 500, ""
                
                if response.status_code == 429:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    
                    if "quota" in error_msg.lower():
                        logger.error(f"[GPT API] Quota exceeded")
                        return 429, "QUOTA_EXCEEDED"
                    
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning(f"[GPT API] Rate limited, waiting {delay}s")
                    await asyncio.sleep(delay)
                    continue
                
                logger.error(f"[GPT API] Error {response.status_code}: {response.text[:500]}")
                last_error = response.status_code
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    
        except httpx.TimeoutException:
            logger.error(f"[GPT API] Timeout")
            last_error = 504
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
                
        except Exception as e:
            logger.exception(f"[GPT API] Error: {e}")
            last_error = 500
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
    
    return last_error or 500, ""