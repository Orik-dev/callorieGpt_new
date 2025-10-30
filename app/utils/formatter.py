from chatgpt_md_converter import telegram_format

def format_answer(text: str, daily_totals: dict = None) -> str:
    formatted = telegram_format(text)
    return formatted
