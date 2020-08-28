import os
import sys
import re
import argparse
import wave
import uuid
import psycopg2
from psycopg2 import sql
from datetime import datetime
from tinkoff_voicekit_client import ClientSTT
import config


def recognize(filename, audio_config):
    client = ClientSTT(config.API_KEY, config.SECRET_KEY)
    return client.recognize(filename, audio_config)


def stage_one(text):
    text = text.lower()
    am_words = ["автоответчик", "оставьте сообщение", "после сигнала", "после гудка"]
    for word in am_words:
        if text.find(word) != -1:
            return "Автоответчик"
    if len(text) != 0:
        return "Человек"
    return "Пустая запись"


def stage_two(text):
    positive_words = ["слушаю", "могу", "говорите", "удобно", "хорошо", "давайте"]
    negative_words = ["занят", "нет", "до свидания", "не могу", "неудобно"]
    for word in positive_words:
        if text.find(word) != -1:
            return "Положительно"
    for word in negative_words:
        if text.find(word) != -1:
            return "Отрицательно"
    return "Не распознано"


def get_config(filename):
    """
    Получение конфигурации аудиозаписи
    :param filename: Имя или путь к файлу с аудио
    :return: ({ Словарь содержащий: кодировку, частоту, количество каналов }, длительность аудио )
    """
    wav = wave.open(filename, mode='r')
    config = {
        "encoding": "LINEAR16",
        "sample_rate_hertz": wav.getframerate(),
        "num_channels": wav.getnchannels()
    }
    duration = round(wav.getnframes() / wav.getframerate(), 2)
    wav.close()
    return config, duration


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', required=True, type=str,
                        help="Путь к файлу")
    parser.add_argument('--phone', required=True, type=str,
                        help="Телефонный номер собеседника")
    parser.add_argument('--stage', type=int, required=True,
                        help="Этап распознования: " +
                        "1 - Автоотвечтик или человек, " +
                        "2 - Положительный или отрицательный ответ")
    parser.add_argument('--dbwrite', type=int, default=False,
                        help="Записывать результат в бузу данных: 0 или 1, по умолчанию - 0")

    namespace = parser.parse_args()
    return {
        'filename': namespace.filename,
        'phone': namespace.phone,
        'stage': namespace.stage,
        'dbwrite': namespace.dbwrite
    }


def check_args(args):
    if args['stage'] not in [1, 2]:
        raise ValueError("Параметр stage принимает только значения 1 или 2")
    phone = "".join(re.findall(r'\d', args['phone']))
    if len(phone) != 11:
        raise ValueError("Неверно задан параметр phone")
    args['phone'] = phone
    if not os.path.exists(args['filename']):
        raise ValueError("Файла %s не существует" % args['filename'])


def log_error(error):
    message = str(error) + "\n" + \
              ("Параметры запуска: %s \n" % " ".join(sys.argv)) + \
              str(datetime.now()) + "\n" + \
              "-" * 60 + "\n\n"

    with open(config.ERROR_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(message)


def log_result(data):
    message = data["date"] + "; " + data["time"] + "; " +\
        data["uuid"] + "; " + data["result"] + "; " + data["phone"] + "; " + \
        str(data["duration"]) + "; " + data["text"] + "\n\n"

    with open(config.RESULT_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(message)


def write_to_db(data):
    conn = psycopg2.connect(
        database=config.DB_NAME,
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD
    )
    with conn.cursor() as cursor:
        conn.autocommit = True
        values = (data["date"], data["time"], data["uuid"], data["result"],
                   data["phone"], str(data["duration"]), data["text"])
        table = config.DB_TABLE
        insert = sql.SQL("INSERT INTO {0} (date, time, uuid, result, phone, duration, answer_text) VALUES ({1})").\
            format(sql.Identifier(table), sql.SQL(',').join(map(sql.Literal, values)))
        cursor.execute(insert)


def reformat_data(data):
    """
    Подгтовка результата к записи
    :param data: Словарь с параметрами запуска, результатом распознования и обработки, длительностью файла
    :return: Словарь с параметрами для итоговой записи
    """
    dt = str(datetime.now())
    date, time = dt.split()
    date = "/".join(date.split('-'))
    time = time[:8]
    uid = uuid.uuid4()
    return {
        "date": date,
        "time": time,
        "uuid": str(uid),
        "result": data["result"],
        "phone": data["phone"],
        "duration": data["duration"],
        "text": data["text"]
    }


def main():
    data = create_parser()
    check_args(data)

    audio_config, data['duration'] = get_config(data['filename'])
    print("Параметры файла:", audio_config)

    answer = recognize(data['filename'], audio_config)
    text = answer[0]['alternatives'][0]['transcript']
    data["text"] = text
    print("Распознанный текст: ", text)

    if data['stage'] == 1:
        result = stage_one(text)
    else:
        result = stage_two(text)
    data['result'] = result
    print("Результат проверки: ", result)

    result_data = reformat_data(data)
    log_result(result_data)
    print("Лог записан")
    if data['dbwrite']:
        write_to_db(result_data)
        print("Запись в бд добавлена")

    os.remove(data['filename'])
    print("Файл %s удалён" % data['filename'])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(e)
