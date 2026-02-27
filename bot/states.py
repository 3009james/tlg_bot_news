from aiogram.fsm.state import State, StatesGroup


class SourceWizardState(StatesGroup):
    waiting_name = State()
    waiting_type = State()
    waiting_base_url = State()
    waiting_priority = State()
    waiting_domains = State()
    waiting_settings = State()


class CredentialWizardState(StatesGroup):
    waiting_label = State()
    waiting_secret_name = State()
    waiting_value = State()
