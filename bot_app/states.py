from aiogram.fsm.state import State, StatesGroup


class SupportStates(StatesGroup):
    waiting_for_feedback = State()
    in_chat = State()


class RegistrationStates(StatesGroup):
    waiting_consent = State()
    waiting_phone = State()
    waiting_phone_organic = State()


class AdminStates(StatesGroup):
    waiting_stock_quantity = State()
    # Product wizard
    add_title = State()
    add_price = State()
    add_category = State()
    add_sizes = State()
    add_stock = State()
    add_photos = State()
    add_description = State()
    add_collection = State()
    add_confirm = State()
    # Collection wizard
    col_name = State()
    col_description = State()
