from aiogram.fsm.state import State, StatesGroup


class SupportStates(StatesGroup):
    waiting_for_feedback = State()
    in_chat = State()


class RegistrationStates(StatesGroup):
    waiting_consent = State()
    waiting_phone = State()
    waiting_phone_organic = State()
