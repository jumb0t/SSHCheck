import paramiko
import asyncio
import aiofiles
import socket
import logging
import threading
import time
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

# Класс для цветовой подсветки вывода в консоль
class Colors:
    """Класс Colors содержит ANSI escape последовательности для цветовой
    подсветки текста в консоли. Используется для улучшения читаемости
    выводимой информации."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'      # Зеленый цвет для успешных сообщений
    WARNING = '\033[93m'      # Желтый цвет для предупреждений
    ERROR = '\033[91m'        # Красный цвет для ошибок
    CRITICAL = '\033[41m'     # Красный фон для критических ошибок
    ENDC = '\033[0m'          # Сброс цветового оформления
    BOLD = '\033[1m'          # Жирный текст
    UNDERLINE = '\033[4m'     # Подчеркнутый текст
    PURPLE = '\033[95m'       # Фиолетовый цвет для времени в логах
    ORANGE = '\033[33m'       # Оранжевый цвет для IP-адресов
    DARK_ORANGE = '\033[38;5;208m'  # Темно-оранжевый для сообщений
    INFO = '\033[96m'         # Голубой цвет для информационных сообщений

# Блокировка для синхронизации доступа к выводу в консоль из разных потоков
print_lock = threading.Lock()

class CustomFormatter(logging.Formatter):
    """Пользовательский форматтер для логирования, который добавляет цветовую
    подсветку времени и уровня логов в сообщениях."""
    def format(self, record):
        """Форматирует сообщение логирования с цветовой подсветкой.

        Параметры:
            record (LogRecord): Запись логирования.

        Возвращает:
            str: Отформатированное сообщение.
        """
        levelname = record.levelname   # Уровень логирования (INFO, WARNING, ERROR и т.д.)
        message = record.getMessage()  # Само сообщение
        asctime = self.formatTime(record, self.datefmt)  # Время записи

        # Цветовая подсветка уровня логирования
        if levelname == 'INFO':
            levelname_color = f"{Colors.INFO}{levelname}{Colors.ENDC}"
        elif levelname == 'WARNING':
            levelname_color = f"{Colors.WARNING}{levelname}{Colors.ENDC}"
        elif levelname == 'ERROR':
            levelname_color = f"{Colors.ERROR}{levelname}{Colors.ENDC}"
        elif levelname == 'CRITICAL':
            levelname_color = f"{Colors.CRITICAL}{levelname}{Colors.ENDC}"
        else:
            levelname_color = levelname

        # Цветовая подсветка времени
        asctime_color = f"{Colors.PURPLE}{asctime}{Colors.ENDC}"

        # Подсветка IP-адресов в сообщении (замена IP на цветной вариант)
        ip_address_pattern = re.compile(r'\d+\.\d+\.\d+\.\d+')
        message_color = ip_address_pattern.sub(
            lambda match: f"{Colors.ORANGE}{match.group(0)}{Colors.ENDC}", message)
        # Общая цветовая подсветка сообщения
        message_color = f"{Colors.DARK_ORANGE}{message_color}{Colors.ENDC}"

        # Формирование окончательного отформатированного сообщения
        formatted_message = f"{asctime_color} - {levelname_color} - {message_color}"

        return formatted_message

def setup_logging():
    """Настраивает систему логирования.

    Создает обработчики для разных уровней логов, форматирует вывод и
    добавляет цветовую подсветку для консольного вывода.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Словарь с обработчиками для разных уровней логирования и соответствующими файлами
    handlers = {
        logging.DEBUG: 'debug.log',
        logging.INFO: 'info.log',
        logging.WARNING: 'warning.log',
        logging.ERROR: 'error.log',
        logging.CRITICAL: 'critical.log'
    }

    # Инициализация пользовательского форматтера с цветовой подсветкой
    formatter = CustomFormatter()

    # Создание консольного обработчика с цветовой подсветкой
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Создание файловых обработчиков для каждого уровня логирования
    for level, filename in handlers.items():
        file_handler = logging.FileHandler(filename)
        file_handler.setLevel(level)
        # Используем стандартный форматтер без цветовой подсветки для файлов
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)

def load_config(file_path='config.json'):
    """Загружает конфигурационные параметры из JSON-файла.

    Параметры:
        file_path (str): Путь к файлу конфигурации.

    Возвращает:
        dict: Словарь с конфигурационными параметрами.

    Исключения:
        FileNotFoundError: Если файл конфигурации не найден.
        json.JSONDecodeError: Если файл содержит некорректный JSON.
    """
    with open(file_path, 'r') as file:
        return json.load(file)

async def check_ssh_credentials(host, port, username, password, config, success_file):
    """Проверяет SSH-учетные данные для указанного хоста.

    Пытается установить SSH-соединение с заданными учетными данными.
    В случае успешной аутентификации записывает результат в файл.

    Параметры:
        host (str): IP-адрес или имя хоста.
        port (int): Порт SSH (обычно 22).
        username (str): Имя пользователя для входа.
        password (str): Пароль пользователя.
        config (dict): Конфигурационные параметры из файла.
        success_file (str): Путь к файлу для записи успешных попыток.

    Возвращает:
        dict: Словарь с результатом проверки (статус и сообщение).
    """
    # Инициализация результата проверки
    result = {
        'host': host,
        'port': port,
        'username': username,
        'status': 'Failed',  # По умолчанию считаем, что попытка не удалась
        'message': ''
    }
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Автоматическое добавление неизвестных ключей хоста

    ssh_config = config['ssh']
    timeout = ssh_config.get('timeout', 10)  # Тайм-аут по умолчанию 10 секунд
    max_retries = ssh_config.get('max_retries', 1)  # Количество попыток по умолчанию 1

    for attempt in range(max_retries):
        try:
            # Попытка установить SSH-соединение
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                auth_timeout=ssh_config.get('auth_timeout', timeout),
                banner_timeout=ssh_config.get('banner_timeout', timeout),
                allow_agent=ssh_config.get('allow_agent', False),
                look_for_keys=ssh_config.get('look_for_keys', False)
            )
            # Если соединение установлено успешно
            result['status'] = 'Success'
            result['message'] = 'Authentication successful'
            with print_lock:
                print(f"{Colors.OKGREEN}Success{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.info(f"Authentication successful for {host}:{port} with {username}")

            # Асинхронная запись успешной попытки в файл
            async with aiofiles.open(success_file, 'a') as file:
                await file.write(f"{host}:{port};{username};{password}\n")
            client.close()
            break  # Выходим из цикла после успешной попытки
        except paramiko.AuthenticationException:
            # Ошибка аутентификации (неверные учетные данные)
            result['message'] = 'Authentication failed'
            with print_lock:
                print(f"{Colors.WARNING}Warning{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.warning(f"Authentication failed for {host}:{port} with {username}")
            break  # Прерываем попытки при ошибке аутентификации
        except paramiko.BadHostKeyException as e:
            # Некорректный ключ хоста
            result['message'] = f'Bad host key: {e}'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"Bad host key for {host}:{port}: {e}")
            break  # Прерываем попытки при ошибке ключа хоста
        except paramiko.SSHException as e:
            # Общая ошибка SSH
            result['message'] = f'SSHException: {e}'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"SSHException for {host}:{port} with {username}: {e}")
            await asyncio.sleep(2)  # Задержка перед повторной попыткой
        except socket.timeout:
            # Превышено время ожидания соединения
            result['message'] = 'Connection timed out'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"Connection timed out for {host}:{port} with {username}")
            await asyncio.sleep(2)  # Задержка перед повторной попыткой
        except socket.error as e:
            # Ошибка сокета (проблемы с сетью)
            result['message'] = f'Socket error: {e}'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"Socket error for {host}:{port} with {username}: {e}")
            await asyncio.sleep(2)  # Задержка перед повторной попыткой
        except Exception as e:
            # Неизвестная ошибка
            result['message'] = f'Unknown error: {e}'
            with print_lock:
                print(f"{Colors.CRITICAL}Critical{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.critical(f"Unknown error for {host}:{port} with {username}: {e}")
            break  # Прерываем попытки при неизвестной ошибке

    return result

async def load_credentials(file_path):
    """Загружает список учетных данных из файла.

    Файл должен содержать строки в формате:
    <IP-адрес>:<порт>;<имя пользователя>;<пароль>

    Параметры:
        file_path (str): Путь к файлу с учетными данными.

    Возвращает:
        list: Список кортежей (host, port, username, password).

    Исключения:
        FileNotFoundError: Если файл не найден.
        Exception: При возникновении ошибок чтения файла.
    """
    credentials = []
    try:
        # Асинхронное открытие файла для чтения
        async with aiofiles.open(file_path, 'r') as file:
            async for line in file:
                line = line.strip()  # Удаляем пробелы и переводы строк
                if line and not line.startswith('#'):
                    parts = line.split('|')[0].strip()  # Отбрасываем комментарии после '|'
                    if ';' in parts:
                        # Разбиваем строку на компоненты
                        host_port, username, password = parts.split(';')
                        try:
                            host, port = host_port.split(':')
                            port = int(port)
                            if not (0 <= port <= 65535):
                                raise ValueError("Invalid port number")
                            # Валидация IP-адреса
                            socket.inet_aton(host)
                            credentials.append((host, port, username, password))
                        except ValueError as ve:
                            # Ошибка в формате строки или некорректный порт
                            with print_lock:
                                print(f"{Colors.WARNING}Warning{Colors.ENDC} - Неверный формат строки: {line} ({ve})")
                            logging.warning(f"Неверный формат строки: {line} ({ve})")
                    else:
                        # Строка не содержит разделителя ';', неверный формат
                        with print_lock:
                            print(f"{Colors.WARNING}Warning{Colors.ENDC} - Неверный формат строки: {line}")
                        logging.warning(f"Неверный формат строки: {line}")
    except FileNotFoundError:
        # Файл с учетными данными не найден
        with print_lock:
            print(f"{Colors.ERROR}Error{Colors.ENDC} - Файл не найден: {file_path}")
        logging.error(f"Файл не найден: {file_path}")
    except Exception as e:
        # Общая ошибка при чтении файла
        with print_lock:
            print(f"{Colors.ERROR}Error{Colors.ENDC} - Ошибка чтения файла: {e}")
        logging.error(f"Ошибка чтения файла {file_path}: {e}")
    return credentials

async def check_credentials_in_threads(credentials, max_workers, config, success_file):
    """Проверяет учетные данные, используя пул потоков для параллелизации.

    Параметры:
        credentials (list): Список учетных данных для проверки.
        max_workers (int): Максимальное количество потоков в пуле.
        config (dict): Конфигурационные параметры.
        success_file (str): Путь к файлу для записи успешных попыток.

    Возвращает:
        list: Список результатов проверки для каждой пары учетных данных.
    """
    loop = asyncio.get_running_loop()
    results = []

    # Функция-обертка для запуска асинхронной функции в потоке
    def run_check_ssh(cred):
        return asyncio.run(check_ssh_credentials(*cred, config, success_file))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Создаем задачи для выполнения в пуле потоков
        tasks = [
            loop.run_in_executor(
                executor, run_check_ssh, cred
            )
            for cred in credentials
        ]
        # Собираем результаты выполнения всех задач
        for result in await asyncio.gather(*tasks):
            results.append(result)

    return results

def print_statistics(results, start_time):
    """Выводит статистику работы скрипта после завершения проверки.

    Параметры:
        results (list): Список результатов проверки.
        start_time (float): Время начала выполнения скрипта.
    """
    total_ips = len(results)  # Общее количество проверенных IP-адресов
    successful = sum(1 for r in results if r['status'] == 'Success')  # Количество успешных попыток
    errors = sum(1 for r in results if r['status'] == 'Failed')  # Количество неудачных попыток
    end_time = time.time()
    duration = end_time - start_time  # Общее время выполнения скрипта

    # Вывод статистики с цветовой подсветкой
    print(f"\n{Colors.BOLD}Статистика выполнения:{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Успешные попытки: {successful}{Colors.ENDC}")
    print(f"{Colors.WARNING}Ошибки: {errors}{Colors.ENDC}")
    print(f"{Colors.INFO}Общее количество проверенных IP: {total_ips}{Colors.ENDC}")
    print(f"{Colors.INFO}Время выполнения: {duration:.2f} секунд{Colors.ENDC}")

async def main(credentials_file):
    """Главная функция скрипта, orchestrator.

    Загружает конфигурацию, учетные данные, запускает проверку и выводит статистику.

    Параметры:
        credentials_file (str): Путь к файлу с учетными данными.
    """
    setup_logging()  # Настройка логирования
    config = load_config()  # Загрузка конфигурации

    start_time = time.time()  # Запоминаем время начала выполнения
    success_file = config['ssh'].get('success_file', 'success.txt')  # Файл для успешных попыток
    max_workers = config['async'].get('max_workers', 10)  # Максимальное количество потоков

    # Проверка наличия файла с учетными данными
    if not os.path.isfile(credentials_file):
        print(f"{Colors.ERROR}Ошибка: Файл не найден: {credentials_file}{Colors.ENDC}")
        sys.exit(1)

    # Загрузка учетных данных
    credentials = await load_credentials(credentials_file)
    if not credentials:
        # Если список учетных данных пуст, завершаем работу
        print(f"{Colors.ERROR}Ошибка: Нет учетных данных для проверки.{Colors.ENDC}")
        sys.exit(1)

    # Проверка учетных данных в потоках
    results = await check_credentials_in_threads(credentials, max_workers, config, success_file)

    # Вывод статистики выполнения
    print_statistics(results, start_time)

if __name__ == '__main__':
    # Проверка аргументов командной строки
    if len(sys.argv) != 2:
        print(f"Использование: {sys.argv[0]} <путь_к_файлу_учетных_данных>")
        sys.exit(1)

    credentials_file = sys.argv[1]
    try:
        # Запуск главной асинхронной функции
        asyncio.run(main(credentials_file))
    except KeyboardInterrupt:
        # Обработка прерывания выполнения пользователем (Ctrl+C)
        print(f"\n{Colors.WARNING}Прерывание выполнения пользователем.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        # Обработка общих исключений
        print(f"{Colors.CRITICAL}Ошибка: {e}{Colors.ENDC}")
        logging.critical(f"Ошибка: {e}")
        sys.exit(1)
