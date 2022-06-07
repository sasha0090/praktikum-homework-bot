import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import BadHTTPStatus, TokenLack

load_dotenv()


PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ANTISPAM_TIME = 10
RETRY_TIME = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}


HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))


def send_message(bot, message):
    """Отправляем сообщение в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as exc:
        logger.error("Не удается отправить сообщение в телеграм.\n"
                     f"Ошибка: {exc}")
        return False

    logger.info(f"Отправили сообщение: {message}")
    return True


def get_api_answer(current_timestamp):
    """Делаем запрос к эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {"from_date": timestamp}
    logger.info("Запрос к эндпоинту")
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except Exception as exc:
        logger.error(f"Проблема с подключением к эндпоинту {ENDPOINT}")
        raise exc

    # Хотел написать: if not response.ok, но тест не пропускает
    # AttributeError: 'MockResponseGET' object has no attribute 'ok'
    if response.status_code == HTTPStatus.OK:
        logger.error(
            "(＞︿＜) "
            f"Эндпоинт {ENDPOINT} недоступен."
            f"Код ответа API: {response.status_code}"
        )
        raise BadHTTPStatus("Код ответа от API не 200.")
    return response.json()


def check_response(response: dict):
    """Проверяет ответ API на корректность и соответствует ожиданиям."""
    if not isinstance(response, dict):
        raise TypeError("Ответ не словарь")
    logger.info("Получаем homeworks")

    homeworks = response.get("homeworks")

    if homeworks is None:
        raise KeyError("Не нашли homeworks в ответе")
    if not isinstance(homeworks, list):
        raise TypeError("homeworks не список")
    if not homeworks:
        logger.info("Не найдены homeworks")

    return homeworks


def parse_status(homework: dict):
    """Извлекает из информации и статус конкретной домашней работы."""
    # Достаем по ключам информацию.
    # Если ключа нет, то логирование и обработка исключения в main'е
    homework_name = homework.get("homework_name")
    homework_status = homework.get("status")

    if homework_name is None:
        raise KeyError("Не нашли homework_name в homework")
    if homework_status is None:
        raise KeyError("Не нашли status в homework")

    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if verdict is None:
        raise KeyError(
            f"Недокументированный статус {homework_name}"
            " домашней работы в ответе API"
        )

    logger.info(f"Получили новый статус {homework_name} - {verdict}")
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }

    try:
        for key, value in tokens.items():
            if not value:
                raise TokenLack(
                    "Отсутствует обязательная " f"переменная окружения: {key}"
                )
    except TokenLack as exc:
        logger.critical(exc)
        return False

    logger.debug("Проверили переменные окружения, все подгружены")
    return True


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_exc_message = ""
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response["current_date"]
            homeworks = check_response(response)

            # Отправляем все статусы за последние RETRY_TIME секунд
            while homeworks:
                homework = homeworks.pop()
                message = parse_status(homework)

                send_message(bot, message)
                time.sleep(ANTISPAM_TIME)

        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logger.error(message)
            if last_exc_message != message:
                successfully_sending: bool = send_message(bot, message)
                if successfully_sending:
                    last_exc_message = message

        logger.info(f"Ждем {RETRY_TIME} секунд")
        time.sleep(RETRY_TIME)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s  [%(levelname)s]  %(message)s", level=logging.INFO
    )

    if check_tokens():
        logger.info("Запуск бота")
        main()
    else:
        logger.critical("Программа принудительно остановлена.")
