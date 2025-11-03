import logging
from app.api.gpt import ai_request
from app.services.user import get_user_by_id
from app.services.meals import (
    parse_gpt_response,
    save_meals,
    get_today_summary,
    MealParseError
)
from app.utils.messages import send_text, edit_text, delete_message
from app.db.mysql import mysql

logger = logging.getLogger(__name__)


async def process_gpt_request(
    ctx,
    user_id: int,
    message_id: int,
    chat_id: int,
    text: str = None,
    image_url: str = None
):
    """
    Обрабатывает запрос к GPT и сохраняет результат
    
    НОВАЯ ЛОГИКА:
    - Не используем контекст из Redis
    - Парсим JSON ответ с валидацией
    - Сохраняем в БД
    - Показываем итоги дня
    - Атомарно списываем токен в конце
    """
    try:
        # 1. Получаем данные пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Пользователь не найден. Используйте /start"
            )
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        
        # 2. Получаем текущие итоги дня для контекста
        summary = await get_today_summary(user_id, user_tz)
        
        # 3. Формируем контекстный промпт
        context_text = text or "Определи блюдо на фото и рассчитай КБЖУ"
        
        if summary["meals"]:
            context_text += "\n\n📊 Сегодня уже добавлено:\n"
            for meal in summary["meals"]:
                context_text += (
                    f"- {meal['food_name']}: "
                    f"{float(meal['calories']):.0f}ккал\n"
                )
        
        # 4. Запрос к GPT
        logger.info(f"[GPT Queue] User {user_id}: requesting GPT")
        code, raw_response = await ai_request(
            user_id=user_id,
            text=context_text,
            image_link=image_url
        )
        
        if code != 200:
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Не удалось получить ответ от AI. Попробуйте позже."
            )
            return
        
        # 5. Парсим ответ
        try:
            parsed_data = await parse_gpt_response(raw_response)
            logger.info(
                f"[GPT Queue] User {user_id}: parsed {len(parsed_data['items'])} items"
            )
        except MealParseError as e:
            logger.error(f"[GPT Queue] User {user_id}: parse error: {e}")
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Не удалось распознать блюдо.\n\n"
                "Попробуйте:\n"
                "• Сфотографировать четче при хорошем освещении\n"
                "• Описать текстом (например: 'гречка 200г с курицей 150г')\n"
                "• Указать точный вес продуктов"
            )
            return
        
        # 6. Сохраняем в БД
        try:
            await save_meals(user_id, parsed_data, user_tz, image_file_id=None)
            logger.info(f"[GPT Queue] User {user_id}: saved to DB")
        except Exception as e:
            logger.exception(f"[GPT Queue] User {user_id}: DB save error: {e}")
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Ошибка сохранения данных. Попробуйте еще раз."
            )
            return
        
        # 7. Получаем обновленные итоги
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        # 8. Формируем красивый ответ
        response = "✅ <b>Добавлено:</b>\n\n"
        
        for item in parsed_data["items"]:
            response += (
                f"🍽 <b>{item['name']}</b>\n"
                f"   Вес: {int(item['weight_grams'])}г\n"
                f"   Калории: {item['calories']:.1f} ккал\n"
                f"   БЖУ: {item['protein']:.1f}г • "
                f"{item['fat']:.1f}г • {item['carbs']:.1f}г\n"
            )
            
            # Показываем уверенность если низкая
            confidence = item.get("confidence", 1.0)
            if confidence < 0.7:
                response += f"   ⚠️ Примерная оценка (уверенность: {confidence:.0%})\n"
            
            response += "\n"
        
        # Добавляем заметки от GPT если есть
        if parsed_data.get("notes"):
            response += f"💡 <i>{parsed_data['notes']}</i>\n\n"
        
        # Итоги дня
        response += "━━━━━━━━━━━━━━━━\n"
        response += f"📊 <b>Итого за день:</b>\n"
        response += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        response += f"🥩 Белки: {float(totals['total_protein']):.1f}г\n"
        response += f"🧈 Жиры: {float(totals['total_fat']):.1f}г\n"
        response += f"🍞 Углеводы: {float(totals['total_carbs']):.1f}г\n"
        response += f"🍽 Приемов пищи: {totals['meals_count']}\n\n"
        response += "Используйте /today для детального просмотра"
        
        # 9. Отправляем ответ
        await edit_text(chat_id, message_id, response)
        
        # 10. АТОМАРНО списываем токен (защита от отрицательных значений)
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """UPDATE users_tbl 
                       SET free_tokens = GREATEST(free_tokens - 1, 0)
                       WHERE tg_id = %s""",
                    (user_id,)
                )
        
        logger.info(f"[GPT Queue] User {user_id}: success, token deducted")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] User {user_id}: critical error: {e}")
        try:
            await delete_message(chat_id, message_id)
            await send_text(
                chat_id,
                "⚠️ Произошла ошибка при обработке. "
                "Попробуйте еще раз или обратитесь в поддержку."
            )
        except Exception:
            pass