from aiogram.fsm.state import State, StatesGroup


class BroadcastState(StatesGroup):
    waiting_for_text = State()


class ProfileSetupState(StatesGroup):
    waiting_birth_year = State()
    waiting_height = State()
    waiting_weight = State()


class ManualGoalState(StatesGroup):
    waiting_calories = State()
    waiting_protein = State()
    waiting_fat = State()
    waiting_carbs = State()
