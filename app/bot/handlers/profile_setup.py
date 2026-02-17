# app/bot/handlers/profile_setup.py
"""
Wizard настройки профиля: пол → год рождения → рост → вес → активность → цель → результат.
Вызывается из:
1. После выбора таймзоны в /start (новые пользователи)
2. Кнопка «Настроить цель калорий» в /profile (существующие)
"""
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from app.bot.states.broadcast_state import ProfileSetupState
from app.services.user import (
    save_user_profile,
    calculate_bmr_tdee,
)
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)

FITNESS_GOAL_LABELS = {
    "lose": "Похудеть",
    "gain": "Набрать мышечную массу",
    "maintain": "Поддержание формы",
}


# ============================================
# КЛАВИАТУРЫ
# ============================================

def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Мужской", callback_data="profile_setup:gender:male"
            ),
            InlineKeyboardButton(
                text="Женский", callback_data="profile_setup:gender:female"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Пропустить настройку",
                callback_data="profile_setup:skip"
            ),
        ],
    ])


def activity_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "sedentary":   "🪑 Сидячий (офис)",
        "light":       "🚶 Лёгкая (1-3 раза/нед)",
        "moderate":    "🏃 Умеренная (3-5 раз/нед)",
        "active":      "💪 Высокая (6-7 раз/нед)",
        "very_active": "🔥 Очень высокая (2 раза/день)",
    }
    rows = [
        [InlineKeyboardButton(
            text=label, callback_data=f"profile_setup:activity:{key}"
        )]
        for key, label in labels.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fitness_goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔥 Похудеть", callback_data="profile_setup:goal:lose"
        )],
        [InlineKeyboardButton(
            text="💪 Набрать мышечную массу", callback_data="profile_setup:goal:gain"
        )],
        [InlineKeyboardButton(
            text="⚖️ Поддержание формы", callback_data="profile_setup:goal:maintain"
        )],
    ])


# ============================================
# ПРОПУСК
# ============================================

@router.callback_query(F.data == "profile_setup:skip")
async def handle_skip_setup(callback: CallbackQuery, state: FSMContext):
    """Пользователь пропустил настройку"""
    await state.clear()
    await callback.answer("Пропущено")
    await callback.message.edit_text(
        "Настройка пропущена.\n\n"
        "Будет использоваться стандартная цель — 2000 ккал/день.\n"
        "Настроить можно в любой момент: /profile",
        parse_mode="HTML"
    )


# ============================================
# ШАГ 1: Пол (callback)
# ============================================

@router.callback_query(
    F.data.in_({"profile_setup:gender:male", "profile_setup:gender:female"})
)
async def handle_gender(callback: CallbackQuery, state: FSMContext):
    """Шаг 1 → 2: пол выбран, спрашиваем год рождения"""
    gender = callback.data.split(":")[-1]
    await state.update_data(profile_gender=gender)
    await state.set_state(ProfileSetupState.waiting_birth_year)

    await callback.answer()
    await callback.message.edit_text(
        "<b>Год рождения</b>\n\n"
        "Введите год рождения (например, <code>1990</code>):",
        parse_mode="HTML"
    )


# ============================================
# ШАГ 2: Год рождения (FSM)
# ============================================

@router.message(ProfileSetupState.waiting_birth_year)
async def handle_birth_year(message: Message, state: FSMContext):
    """Шаг 2 → 3: год рождения → рост"""
    if not message.text:
        await message.answer("Пожалуйста, введите год рождения числом.")
        return

    text = message.text.strip()

    try:
        year = int(text)
    except ValueError:
        await message.answer(
            "Введите год числом, например <code>1990</code>",
            parse_mode="HTML"
        )
        return

    current_year = datetime.now().year
    age = current_year - year

    if age < 14 or age > 100:
        await message.answer(
            "Пожалуйста, введите корректный год рождения (возраст 14-100)."
        )
        return

    await state.update_data(profile_birth_year=year)
    await state.set_state(ProfileSetupState.waiting_height)

    await message.answer(
        "<b>Рост</b>\n\n"
        "Введите ваш рост в сантиметрах (например, <code>175</code>):",
        parse_mode="HTML"
    )


# ============================================
# ШАГ 3: Рост (FSM)
# ============================================

@router.message(ProfileSetupState.waiting_height)
async def handle_height(message: Message, state: FSMContext):
    """Шаг 3 → 4: рост → вес"""
    if not message.text:
        await message.answer("Пожалуйста, введите рост числом.")
        return

    text = message.text.strip()

    try:
        height = int(text)
    except ValueError:
        await message.answer(
            "Введите рост числом, например <code>175</code>",
            parse_mode="HTML"
        )
        return

    if height < 100 or height > 250:
        await message.answer("Введите рост от 100 до 250 см.")
        return

    await state.update_data(profile_height=height)
    await state.set_state(ProfileSetupState.waiting_weight)

    await message.answer(
        "<b>Вес</b>\n\n"
        "Введите ваш вес в килограммах (например, <code>70</code>):",
        parse_mode="HTML"
    )


# ============================================
# ШАГ 4: Вес (FSM)
# ============================================

@router.message(ProfileSetupState.waiting_weight)
async def handle_weight(message: Message, state: FSMContext):
    """Шаг 4 → 5: вес → активность"""
    if not message.text:
        await message.answer("Пожалуйста, введите вес числом.")
        return

    text = message.text.strip()

    try:
        weight = float(text.replace(",", "."))
    except ValueError:
        await message.answer(
            "Введите вес числом, например <code>70</code>",
            parse_mode="HTML"
        )
        return

    if weight < 30 or weight > 300:
        await message.answer("Введите вес от 30 до 300 кг.")
        return

    await state.update_data(profile_weight=weight)

    await message.answer(
        "<b>Уровень активности</b>\n\n"
        "Выберите ваш обычный уровень физической активности:",
        reply_markup=activity_keyboard(),
        parse_mode="HTML"
    )


# ============================================
# ШАГ 5: Активность (callback) → спрашиваем цель
# ============================================

@router.callback_query(F.data.startswith("profile_setup:activity:"))
async def handle_activity(callback: CallbackQuery, state: FSMContext):
    """Шаг 5 → 6: активность выбрана, спрашиваем цель"""
    activity = callback.data.split(":")[-1]
    await state.update_data(profile_activity=activity)

    await callback.answer()
    await callback.message.edit_text(
        "<b>Какая у вас цель?</b>\n\n"
        "Это влияет на расчёт калорий и нормы белков, жиров, углеводов:",
        reply_markup=fitness_goal_keyboard(),
        parse_mode="HTML"
    )


# ============================================
# ШАГ 6: Цель (callback) → расчёт и сохранение
# ============================================

@router.callback_query(F.data.startswith("profile_setup:goal:"))
async def handle_fitness_goal(callback: CallbackQuery, state: FSMContext):
    """Финал: расчёт КБЖУ, сохранение, показ результата"""
    fitness_goal = callback.data.split(":")[-1]
    data = await state.get_data()

    gender = data.get("profile_gender")
    birth_year = data.get("profile_birth_year")
    height = data.get("profile_height")
    weight = data.get("profile_weight")
    activity = data.get("profile_activity")

    if not all([gender, birth_year, height, weight, activity]):
        await callback.answer(
            "Данные потеряны. Начните заново: /profile",
            show_alert=True
        )
        await state.clear()
        return

    bmr, tdee, calorie_goal, protein_g, fat_g, carbs_g = calculate_bmr_tdee(
        gender=gender,
        weight_kg=weight,
        height_cm=height,
        birth_year=birth_year,
        activity_level=activity,
        fitness_goal=fitness_goal,
    )

    user_id = callback.from_user.id

    try:
        await save_user_profile(
            user_id=user_id,
            gender=gender,
            height_cm=height,
            weight_kg=weight,
            birth_year=birth_year,
            activity_level=activity,
            calorie_goal=calorie_goal,
            fitness_goal=fitness_goal,
            protein_goal=protein_g,
            fat_goal=fat_g,
            carbs_goal=carbs_g,
        )
    except Exception as e:
        logger.exception(f"[ProfileSetup] Error saving for {user_id}: {e}")
        await callback.answer(
            "Ошибка сохранения. Попробуйте позже.",
            show_alert=True
        )
        await state.clear()
        return

    await state.clear()
    await callback.answer("Сохранено!")

    activity_labels = {
        "sedentary":   "Сидячий",
        "light":       "Лёгкая активность",
        "moderate":    "Умеренная активность",
        "active":      "Высокая активность",
        "very_active": "Очень высокая активность",
    }
    gender_label = "Мужской" if gender == "male" else "Женский"
    age = datetime.now().year - birth_year
    goal_label = FITNESS_GOAL_LABELS.get(fitness_goal, fitness_goal)

    await callback.message.edit_text(
        f"<b>Ваш план рассчитан!</b>\n\n"
        f"Пол: {gender_label}\n"
        f"Возраст: {age}\n"
        f"Рост: {height} см\n"
        f"Вес: {weight} кг\n"
        f"Активность: {activity_labels.get(activity, activity)}\n"
        f"Цель: <b>{goal_label}</b>\n\n"
        f"BMR (базовый обмен): <b>{bmr:.0f}</b> ккал\n"
        f"TDEE (с активностью): <b>{tdee:.0f}</b> ккал\n\n"
        f"<b>Ваша дневная норма:</b>\n"
        f"Калории: <b>{calorie_goal}</b> ккал\n"
        f"Белки: <b>{protein_g}</b>г\n"
        f"Жиры: <b>{fat_g}</b>г\n"
        f"Углеводы: <b>{carbs_g}</b>г\n\n"
        f"Изменить: /profile",
        parse_mode="HTML"
    )

    logger.info(
        f"[ProfileSetup] Saved for {user_id}: "
        f"fitness={fitness_goal}, cal={calorie_goal}, "
        f"P={protein_g}g F={fat_g}g C={carbs_g}g"
    )
