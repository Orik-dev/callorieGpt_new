import json
import httpx
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Улучшенный промпт с инструкциями по точной оценке веса
OPENAI_PROMPT = """Ты — точный ассистент по подсчету калорий и нутриентов.

КРИТИЧЕСКИ ВАЖНО: Отвечай ТОЛЬКО валидным JSON без каких-либо пояснений. Формат:

{
  "items": [
    {
      "name": "Название блюда",
      "weight_grams": 200,
      "calories": 450.5,
      "protein": 25.0,
      "fat": 15.0,
      "carbs": 50.0,
      "confidence": 0.85
    }
  ],
  "notes": "Краткий комментарий (опционально)"
}

ПРАВИЛА ОПРЕДЕЛЕНИЯ ВЕСА (критически важно для точности):

1. ВИЗУАЛЬНЫЕ ОРИЕНТИРЫ на фото:
   • Обеденная тарелка: ~24см диаметр
   • Чайная ложка: 5мл/5г
   • Столовая ложка: 15мл/15г
   • Граненый стакан: 200мл
   • Чашка/кружка: 250мл
   • Ладонь взрослого: ~100г белка

2. СТАНДАРТНЫЕ ПОРЦИИ продуктов:
   • Яблоко среднее: 150г
   • Банан без кожуры: 100г
   • Яйцо куриное: 55г
   • Ломтик хлеба: 25-30г
   • Порция риса/гречки готовой: 150г
   • Котлета: 80-100г
   • Куриная грудка: 150-200г
   • Стейк: 200-250г

3. ОЦЕНКА ПО ЗАПОЛНЕННОСТИ тарелки:
   • 1/4 тарелки = ~100-150г
   • 1/2 тарелки = ~200-300г
   • Полная тарелка = ~400-500г

4. ДЛЯ ЖИДКОСТЕЙ:
   • Используй объем в мл
   • Для супов: 1мл ≈ 1г
   • Для масла: 1мл ≈ 0.9г
   • Для молока: 1мл ≈ 1.03г

5. СПОСОБ ПРИГОТОВЛЕНИЯ влияет на КБЖУ:
   • Жареное: +30-50% жиров (масло впитывается)
   • Вареное/паровое: исходные КБЖУ
   • Запеченное с маслом: +20% жиров
   • Тушеное: +10-15% жиров

ПРАВИЛА РАСЧЕТА КБЖУ:

1. Используй точные данные из баз пищевой ценности
2. Для готовых блюд учитывай ВСЕ ингредиенты
3. Для салатов с заправкой: отдельно овощи + заправка
4. Для сложных блюд (пицца, бургер): разбивай на компоненты

CONFIDENCE (уверенность в оценке):
- 0.9-1.0: четко видно продукт И порцию, есть визуальные ориентиры
- 0.7-0.9: видно продукт, вес оценен по аналогам
- 0.5-0.7: продукт определен, но вес очень примерный
- 0.3-0.5: грубая оценка, нужно уточнение

ВАЛИДАЦИЯ результата:
- Все числа положительные
- Калории = (белки × 4) + (жиры × 9) + (углеводы × 4) ± 10%
- Вес в диапазоне 1-2000г для обычной порции
- КБЖУ соответствуют справочным данным

ВАЖНО:
- НЕ пиши текст кроме JSON
- НЕ используй markdown
- НЕ объясняй расчеты
- Всегда указывай ВСЕ поля
- Если не уверен в весе - укажи средний вариант + низкий confidence
"""


async def ai_request(
    user_id: int,
    model: str = None,
    text: str = None,
    image_link: str = None
) -> tuple[int, str]:
    """
    Отправляет запрос к OpenAI API
    
    Args:
        user_id: ID пользователя (для логов)
        model: Модель GPT (по умолчанию из настроек)
        text: Текстовое описание еды
        image_link: Ссылка на фото еды
        
    Returns:
        tuple[status_code, response_text]
        
    Raises:
        Не выбрасывает исключения, возвращает (400, "") при ошибке
    """
    if model is None:
        model = settings.openai_default_model
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Проверка входных данных
            if not text and not image_link:
                logger.warning(f"[GPT] User {user_id}: empty request")
                return 400, ""

            # Формируем сообщения (БЕЗ истории из Redis!)
            messages = [
                {"role": "system", "content": OPENAI_PROMPT}
            ]
            
            # Пользовательское сообщение
            user_content = []
            
            if text:
                user_content.append({
                    "type": "text",
                    "text": text
                })
            
            if image_link:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": image_link,
                        "detail": "high"  # Высокое качество для точности
                    }
                })
            
            messages.append({
                "role": "user",
                "content": user_content
            })

            # Формируем запрос
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.2,  # Низкая температура для детерминизма
                "max_tokens": 2000,
                "response_format": {"type": "json_object"}  # Требуем JSON
            }
            
            headers = {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json"
            }

            logger.info(
                f"[GPT] User {user_id}: sending request "
                f"(model={model}, text={bool(text)}, image={bool(image_link)})"
            )
            
            # Отправляем запрос
            response = await client.post(
                settings.openai_api_url,
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(
                    f"[GPT] User {user_id}: API error {response.status_code}: "
                    f"{response.text[:500]}"
                )
                return 400, ""

            result = response.json()
            reply = result["choices"][0]["message"]["content"]
            
            # Проверка использования токенов
            usage = result.get("usage", {})
            logger.info(
                f"[GPT] User {user_id}: success "
                f"(tokens: {usage.get('total_tokens', 0)}, "
                f"response: {len(reply)} chars)"
            )
            
            return 200, reply

    except httpx.TimeoutException:
        logger.error(f"[GPT] User {user_id}: timeout after 60s")
        return 408, ""
    except httpx.HTTPError as e:
        logger.error(f"[GPT] User {user_id}: HTTP error: {e}")
        return 400, ""
    except Exception as e:
        logger.exception(f"[GPT] User {user_id}: unexpected error: {e}")
        return 400, ""