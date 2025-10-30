# app/utils/audio.py
import os
import logging
import speech_recognition as sr
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

logger = logging.getLogger(__name__)

def ogg_to_text(ogg_path: str) -> str:
    """
    Конвертирует OGG-файл в WAV и распознаёт текст с помощью Google Speech Recognition.
    """
    wav_path = ogg_path.replace(".ogg", ".wav")
    try:
        # Конвертация OGG в WAV
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")
        logger.debug(f"Файл {ogg_path} успешно конвертирован в {wav_path}.")

        # Распознавание голоса
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            # Установите limit для распознавания только части файла, если нужно
            # или energy_threshold для фильтрации шума
            data = recognizer.record(source)
            text = recognizer.recognize_google(data, language="ru-RU") # Русский язык
            logger.info(f"Распознан текст из {wav_path}: '{text}'")
            return text

    except CouldntDecodeError as e:
        logger.error(f"[Audio Error] Не удалось декодировать аудиофайл {ogg_path}: {e}")
        return ""
    except sr.UnknownValueError:
        logger.warning(f"[Audio Error] Google Speech Recognition не смог распознать речь в {wav_path}.")
        return ""
    except sr.RequestError as e:
        logger.error(f"[Audio Error] Ошибка запроса к Google Speech Recognition API; {e}")
        return ""
    except Exception as e:
        logger.exception(f"[Audio Error] Непредвиденная ошибка при обработке аудиофайла {ogg_path}: {e}")
        return ""
    finally:
        # Всегда удаляем временные файлы
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
            logger.debug(f"Удалён временный файл: {ogg_path}")
        if os.path.exists(wav_path):
            os.remove(wav_path)
            logger.debug(f"Удалён временный файл: {wav_path}")