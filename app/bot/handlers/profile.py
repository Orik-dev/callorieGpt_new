from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.services.user import get_user_by_id, block_autopay, FREE_TOKENS_COUNT, SUBSCRIBED_TOKENS_COUNT
from app.services.meals import get_week_stats
from app.config import settings
from datetime import datetime, date
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("profile"))
async def handle_profile(message: types.Message):
    """Показывает профиль пользователя + статистику за неделю"""
    user_id = message.from_user.id

    try:
        user = await get_user_by_id(user_id)

        if not user:
            logger.warning(f"[Profile] User {user_id} not found")
            await message.answer(
                "Профиль не найден. Пожалуйста, начните работу с ботом: /start"
            )
            return

        exp_date_raw = user.get("expiration_date")
        exp_date_str = "нет"
        is_active = False

        if exp_date_raw:
            try:
                if isinstance(exp_date_raw, (datetime, date)):
                    exp_date_obj = exp_date_raw if isinstance(exp_date_raw, date) else exp_date_raw.date()
                    exp_date_str = exp_date_obj.strftime("%d.%m.%Y")
                    is_active = exp_date_obj >= datetime.now().date()
            except Exception as e:
                logger.warning(f"[Profile] Failed to parse date for user {user_id}: {e}")

        autopay_active = user.get("payment_method_id") is not None

        free_tokens = user.get("free_tokens", 0)
        max_tokens = SUBSCRIBED_TOKENS_COUNT if is_active else FREE_TOKENS_COUNT
        tokens_display = f"{free_tokens} из {max_tokens}"

        # Цель калорий (персональная или дефолт)
        calorie_goal = user.get("calorie_goal")
        goal_display = calorie_goal or settings.default_calorie_goal

        fitness_goal = user.get("fitness_goal")
        fitness_labels = {
            "lose": "Похудеть",
            "gain": "Набрать массу",
            "maintain": "Поддержание",
            "custom": "Свои цели",
        }

        profile_text = (
            f"<b>Ваш профиль</b>\n\n"
            f"Подписка до: {exp_date_str}\n"
            f"Запросов осталось: {tokens_display}\n"
            f"Автопродление: {'включено' if autopay_active else 'отключено'}\n"
        )

        # Цель и нормы КБЖУ
        if fitness_goal and calorie_goal:
            p_goal = user.get("protein_goal")
            f_goal = user.get("fat_goal")
            c_goal = user.get("carbs_goal")
            profile_text += (
                f"\n<b>Цель: {fitness_labels.get(fitness_goal, fitness_goal)}</b>\n"
                f"Калории: {goal_display} ккал/день\n"
            )
            if p_goal and f_goal and c_goal:
                profile_text += (
                    f"Белки: {p_goal}г\n"
                    f"Жиры: {f_goal}г\n"
                    f"Углеводы: {c_goal}г\n"
                )
        elif calorie_goal:
            profile_text += f"\nЦель: {goal_display} ккал/день\n"
        else:
            profile_text += f"\nЦель: {goal_display} ккал/день <i>(стандартная)</i>\n"

        if is_active:
            profile_text += "\nПодписка активна"
        else:
            profile_text += "\nОформите подписку: /subscribe"

        # СТАТИСТИКА ЗА НЕДЕЛЮ
        user_tz = user.get("timezone", "Europe/Moscow")
        week_stats = await get_week_stats(user_id, user_tz)

        if week_stats and week_stats.get("days_tracked", 0) > 0:
            profile_text += "\n\n━━━━━━━━━━━━━━━━"
            profile_text += "\n📊 <b>Статистика за неделю:</b>\n\n"
            profile_text += f"🔥 Средние калории: <b>{week_stats['avg_calories']:.0f}</b> ккал/день\n"
            profile_text += f"🥗 Дней с записями: <b>{week_stats['days_tracked']}</b> из 7\n"
            profile_text += f"🍽 Всего приемов пищи: <b>{week_stats['total_meals']}</b>\n\n"

            # Персональные рекомендации на основе цели
            avg_cal = week_stats['avg_calories']
            low_threshold = goal_display * 0.6
            ok_low = goal_display * 0.85
            ok_high = goal_display * 1.1

            if avg_cal < low_threshold:
                profile_text += f"⚠️ <i>Слишком мало калорий — рекомендуем {int(ok_low)}-{goal_display} ккал/день</i>"
            elif avg_cal < ok_low:
                profile_text += f"💡 <i>Чуть ниже цели. Рекомендуем {int(ok_low)}-{goal_display} ккал/день</i>"
            elif avg_cal <= ok_high:
                profile_text += "✅ <i>Отличный баланс калорий!</i>"
            else:
                profile_text += "⚠️ <i>Выше цели — следите за активностью</i>"
        else:
            profile_text += "\n\n━━━━━━━━━━━━━━━━"
            profile_text += "\n📊 <b>Статистика за неделю:</b>\n\n"
            profile_text += "📭 <i>Пока нет записей о еде</i>\n"
            profile_text += "Начните добавлять блюда!"

        # Кнопки
        buttons = []

        if not calorie_goal:
            buttons.append([InlineKeyboardButton(
                text="Настроить цель",
                callback_data="profile_setup:start"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text="Изменить цель",
                callback_data="profile_setup:start"
            )])
        buttons.append([InlineKeyboardButton(
            text="Ввести КБЖУ вручную",
            callback_data="manual_goal:start"
        )])

        if autopay_active:
            buttons.append([InlineKeyboardButton(
                text="❌ Отключить автопродление",
                callback_data="cancel_autopay"
            )])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        await message.answer(
            profile_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"[Profile] Shown for user {user_id}: {tokens_display}, goal={goal_display}")

    except Exception as e:
        logger.exception(f"[Profile] Error for user {user_id}: {e}")
        await message.answer(
            "Произошла ошибка при загрузке профиля. "
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(lambda c: c.data == "profile_setup:start")
async def handle_start_profile_setup(callback: CallbackQuery, state: FSMContext):
    """Запускает wizard настройки профиля из /profile"""
    from app.bot.handlers.profile_setup import gender_keyboard
    await callback.message.edit_text(
        "<b>Настройка цели калорий</b>\n\n"
        "Ответьте на несколько вопросов, чтобы рассчитать\n"
        "вашу дневную норму калорий.\n\n"
        "<b>Выберите пол:</b>",
        reply_markup=gender_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_autopay")
async def handle_cancel_autopay(callback: CallbackQuery):
    """Отключает автопродление подписки"""
    user_id = callback.from_user.id

    try:
        await block_autopay(user_id)

        await callback.message.edit_text(
            "✅ <b>Автопродление отключено</b>\n\n"
            "Ваша текущая подписка будет действовать до окончания срока, "
            "после чего не будет продлена автоматически.\n\n"
            "Вы можете оформить новую подписку в любой момент: /subscribe",
            parse_mode="HTML"
        )

        await callback.answer("✅ Автопродление отключено")

        logger.info(f"[Profile] Autopay disabled for user {user_id}")

    except Exception as e:
        logger.exception(f"[Profile] Error disabling autopay for user {user_id}: {e}")
        await callback.answer(
            "Ошибка при отключении автопродления. Попробуйте позже.",
            show_alert=True
        )
