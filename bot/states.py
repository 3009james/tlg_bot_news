from aiogram.fsm.state import State, StatesGroup


class CredentialInputState(StatesGroup):
    waiting_value = State()
