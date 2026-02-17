# app/api/gpt.py
import logging
import asyncio
import httpx
from typing import Tuple
from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

# Singleton httpx client — переиспользует TCP-соединения
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=settings.openai_timeout)
    return _http_client


async def close_client():
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None

SYSTEM_PROMPT = """Ты — эксперт по питанию. Анализируй сообщения пользователя и определяй что он хочет.

ТИПЫ НАМЕРЕНИЙ (intent):
- "add" — добавить еду/напиток в рацион (ПО УМОЛЧАНИЮ для фото и описания)
- "calculate" — только посчитать калории, НЕ добавлять
- "edit" — изменить прием пищи (по названию или последний)
- "delete" — удалить что-то из рациона
- "add_previous" — добавить то, что только что рассчитывали
- "unknown" — непонятно что хочет пользователь

КОГДА ADD (по умолчанию):
- Фото еды/напитка → ВСЕГДА "add" (если нет явного вопроса)
- "съел...", "ел...", "выпил...", "на завтрак/обед/ужин..." → "add"
- Просто название еды или напитка → "add"

ЧТО СЧИТАТЬ (еда И напитки):
- ЕДА: любые блюда, продукты, снеки, десерты, выпечка
- НАПИТКИ: кофе с молоком, латте, капучино, сок, смузи, кола, лимонад, чай с сахаром, пиво, вино, коктейли, кефир, ряженка, молоко, какао и т.д.
- СПОРТПИТ: протеин, гейнер, BCAA, креатин, казеин — это ПРОДУКТЫ, не нутриенты!
- Вода без добавок = 0 ккал (единственное исключение)

ВАЖНО — ПРОДУКТЫ vs НУТРИЕНТЫ:
- "Протеин", "протеиновый коктейль", "whey" — это ПРОДУКТ (порошок/напиток), НЕ нутриент "белок"!
  Пример: "протеин 30г" → name: "Протеин (порошок)", weight_grams: 30, calories: 120, protein: 24, fat: 1, carbs: 3
- Если пользователь указывает конкретные значения КБЖУ (напр. "белки 47, жиры 6, углеводы 3") — используй ИМЕННО ЭТИ значения, пересчитав на указанный вес

КОГДА CALCULATE (только посчитать):
- Явный вопрос: "сколько калорий в...?", "какая калорийность?"
- "посчитай КБЖУ", "а если съесть...?"

КОГДА DELETE:
- "убери", "удали", "отмени", "не ел"
- delete_target: "last" / "all" / название

КОГДА EDIT:
- "там было 150г, не 200", "исправь гречку"
- edit_target: название блюда для поиска, или "last" если не указано

ВРЕМЯ ПРИЁМА:
- Если пользователь указывает время ("в 8 утра", "на завтрак в 9:00", "вчера вечером") → meal_time: "HH:MM"
- Если не указано → НЕ включать meal_time в ответ

ФОРМАТ ОТВЕТА (строго JSON):
{
  "intent": "add|calculate|edit|delete|add_previous|unknown",
  "items": [
    {
      "name": "Полное название продукта/напитка",
      "weight_grams": число,
      "calories": число,
      "protein": число,
      "fat": число,
      "carbs": число
    }
  ],
  "meal_time": "HH:MM (только если указано пользователем)",
  "delete_target": "last|all|название (для delete)",
  "edit_target": "last|название (для edit)",
  "notes": "комментарий"
}

⚠️ КРИТИЧЕСКИ ВАЖНО — РАСЧЁТ КБЖУ:
1. Ты ОБЯЗАН рассчитать РЕАЛЬНЫЕ значения калорий и БЖУ для ЛЮБОЙ еды и напитков!
2. НИКОГДА не возвращай нули! Используй справочные данные о калорийности.
3. Формула проверки: калории ≈ (белки × 4) + (жиры × 9) + (углеводы × 4)
4. Если пользователь указал вес — рассчитай КБЖУ на этот вес
5. Если вес не указан — используй стандартную порцию
6. Для напитков: вес = объём в мл (100мл ≈ 100г)
7. Если на фото видна этикетка с КБЖУ — используй значения с этикетки, пересчитав на вес пользователя

ПРИМЕРЫ:
- "гречка 200г" → weight: 200, cal: 220, p: 8, f: 2, c: 50
- "куриная грудка 150г" → weight: 150, cal: 165, p: 31, f: 3.5, c: 0
- "латте 300мл" → weight: 300, cal: 150, p: 7.5, f: 6, c: 15
- "кола 330мл" → weight: 330, cal: 140, p: 0, f: 0, c: 35
- "пиво 500мл" → weight: 500, cal: 215, p: 1.5, f: 0, c: 18
- "протеин 30г" → weight: 30, cal: 120, p: 24, f: 1, c: 3
- "яблоко" → weight: 180, cal: 85, p: 0.5, f: 0.5, c: 20

❌ ЗАПРЕЩЕНО возвращать нули для реальной еды/напитков!
❌ ЗАПРЕЩЕНО игнорировать КБЖУ с этикетки, если они видны!

Если не уверен — используй средние значения. Лучше примерные, чем нули!
"""


async def ai_request(
    user_id: int,
    text: str,
    image_link: str = None,
    context: str = None,
    history: list[dict] = None,
) -> Tuple[int, str]:
    """Отправляет запрос к OpenAI API"""

    user_message = text
    if context:
        user_message = f"КОНТЕКСТ:\n{context}\n\nЗАПРОС: {text}"

    content = [{"type": "text", "text": user_message}]

    if image_link:
        content.append({
            "type": "image_url",
            "image_url": {"url": image_link, "detail": "high"}
        })

    # Собираем messages: system → история диалога → текущий запрос
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        for entry in history:
            messages.append({
                "role": entry["role"],
                "content": entry["content"],
            })

    messages.append({"role": "user", "content": content})

    payload = {
        "model": settings.openai_default_model,
        "messages": messages,
        "temperature": settings.openai_temperature,
        "max_tokens": settings.openai_max_tokens,
        "response_format": {"type": "json_object"}
    }
    
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"[GPT API] Request for user {user_id} (attempt {attempt + 1})")
            
            client = _get_client()
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
                        logger.warning(
                            f"[GPT API] Content is None! "
                            f"refusal={refusal}, finish_reason={finish_reason}, "
                            f"message={message}"
                        )
                        # Если GPT отказался — ретраить бессмысленно
                        if refusal:
                            return 200, "Не удалось распознать еду на изображении. Попробуйте отправить другое фото или опишите блюдо текстом."
                        # Иначе попробуем ещё раз
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