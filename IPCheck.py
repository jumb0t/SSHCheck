import aiohttp
import asyncio
import json
import logging
import os
import sys
import signal
from aiohttp import ClientSession, ClientTimeout
from asyncio import Semaphore
from colorama import Fore, Style, init

# Инициализация colorama для работы на Windows
init(autoreset=True)

# Константы
API_URL = "https://ipinfo.io/{}/json"  # URL для запроса информации о IP-адресе

# Настройки файла
OUTPUT_FILE = "output.txt"  # Путь к выходному файлу, в который будут записываться результаты
INPUT_FILE = "ssh_checked.txt"  # Путь к входному файлу, содержащему IP-адреса и другую информацию

# Настройки API
TIMEOUT = 0.7 # Таймаут для запросов к API в секундах. Определяет, как долго программа будет ожидать ответа от API

# Настройки параллелизма
MAX_CONCURRENT_REQUESTS = 2  # Максимальное количество одновременных запросов к API. Используется для предотвращения превышения лимита запросов

# Флаги стран в формате Unicode
FLAGS = {
    'AF': '🇦🇫', 'AL': '🇦🇱', 'DZ': '🇩🇿', 'AS': '🇦🇸', 'AD': '🇦🇩', 'AO': '🇦🇴', 'AI': '🇦🇮',
    'AQ': '🇦🇶', 'AG': '🇦🇬', 'AR': '🇦🇷', 'AM': '🇦🇲', 'AW': '🇦🇼', 'AU': '🇦🇺', 'AT': '🇦🇹',
    'AZ': '🇦🇿', 'BS': '🇧🇸', 'BH': '🇧🇭', 'BD': '🇧🇩', 'BB': '🇧🇧', 'BY': '🇧🇾', 'BE': '🇧🇪',
    'BZ': '🇧🇿', 'BJ': '🇧🇯', 'BT': '🇧🇹', 'BO': '🇧🇴', 'BA': '🇧🇦', 'BW': '🇧🇼', 'BV': '🇧🇻',
    'BR': '🇧🇷', 'IO': '🇮🇴', 'BN': '🇧🇳', 'BG': '🇧🇬', 'BF': '🇧🇫', 'BI': '🇧🇮', 'KH': '🇰🇭',
    'CM': '🇨🇲', 'CA': '🇨🇦', 'CV': '🇨🇻', 'KY': '🇰🇾', 'CF': '🇨🇫', 'TD': '🇹🇩', 'CL': '🇨🇱',
    'CN': '🇨🇳', 'CX': '🇨🇽', 'CC': '🇨🇨', 'CO': '🇨🇴', 'KM': '🇰🇲', 'CG': '🇨🇬', 'CD': '🇨🇩',
    'CK': '🇨🇰', 'CR': '🇨🇷', 'CI': '🇨🇮', 'HR': '🇭🇷', 'CU': '🇨🇺', 'CW': '🇨🇼', 'CY': '🇨🇾',
    'CZ': '🇨🇿', 'DK': '🇩🇰', 'DJ': '🇩🇯', 'DM': '🇩🇲', 'DO': '🇩🇴', 'EC': '🇪🇨', 'EG': '🇪🇬',
    'SV': '🇸🇻', 'GQ': '🇬🇶', 'ER': '🇪🇷', 'EE': '🇪🇪', 'ET': '🇪🇹', 'FK': '🇫🇰', 'FO': '🇫🇴',
    'FJ': '🇫🇯', 'FI': '🇫🇮', 'FR': '🇫🇷', 'GF': '🇬🇦', 'PF': '🇵🇫', 'TF': '🇹🇫', 'GA': '🇬🇦',
    'GM': '🇲🇱', 'GE': '🇬🇪', 'DE': '🇩🇪', 'GH': '🇬🇭', 'GI': '🇬🇮', 'GR': '🇬🇷', 'GL': '🇬🇱',
    'GD': '🇬🇩', 'GP': '🇬🇵', 'GU': '🇬🇺', 'GT': '🇵🇪', 'GG': '🇬🇬', 'GN': '🇬🇳', 'GW': '🇬🇼',
    'GY': '🇬🇾', 'HT': '🇭🇹', 'HM': '🇭🇲', 'VA': '🇻🇦', 'HN': '🇭🇳', 'HK': '🇭🇰', 'HU': '🇭🇺',
    'IS': '🇮🇸', 'IN': '🇮🇳', 'ID': '🇮🇩', 'IR': '🇮🇷', 'IQ': '🇮🇶', 'IE': '🇮🇪', 'IM': '🇮🇲',
    'IL': '🇮🇱', 'IT': '🇮🇹', 'JE': '🇯🇪', 'JO': '🇯🇴', 'JP': '🇯🇵', 'KZ': '🇰🇿', 'KE': '🇰🇪',
    'KI': '🇰🇮', 'KP': '🇰🇵', 'KR': '🇰🇷', 'KW': '🇰🇼', 'KG': '🇰🇬', 'LA': '🇱🇦', 'LV': '🇱🇻',
    'LB': '🇱🇧', 'LS': '🇱🇸', 'LR': '🇱🇷', 'LY': '🇱🇾', 'LI': '🇱🇮', 'LT': '🇱🇹', 'LU': '🇱🇺',
    'MO': '🇲🇴', 'MK': '🇲🇰', 'MG': '🇲🇬', 'MW': '🇲🇼', 'MY': '🇲🇾', 'MV': '🇲🇻', 'ML': '🇲🇱',
    'MT': '🇲🇹', 'MH': '🇲🇭', 'MQ': '🇲🇶', 'MR': '🇲🇷', 'MU': '🇲🇺', 'YT': '🇲🇾', 'MX': '🇲🇽',
    'FM': '🇫🇲', 'MD': '🇲🇩', 'MC': '🇲🇨', 'MN': '🇲🇳', 'ME': '🇲🇪', 'MS': '🇲🇸', 'MA': '🇲🇦',
    'MZ': '🇲🇿', 'MM': '🇲🇲', 'NA': '🇳🇦', 'NR': '🇳🇷', 'NP': '🇳🇵', 'NL': '🇳🇱', 'NC': '🇳🇨',
    'NZ': '🇳🇿', 'NI': '🇳🇮', 'NE': '🇳🇪', 'NG': '🇳🇬', 'NU': '🇳🇺', 'NF': '🇳🇫', 'MP': '🇲🇵',
    'NO': '🇳🇴', 'OM': '🇴🇲', 'PK': '🇵🇰', 'PW': '🇵🇼', 'PS': '🇵🇸', 'PA': '🇵🇦', 'PG': '🇵🇬',
    'PY': '🇵🇾', 'PE': '🇵🇪', 'PH': '🇵🇭', 'PN': '🇵🇳', 'PL': '🇵🇱', 'PT': '🇵🇹', 'PR': '🇵🇷',
    'QA': '🇶🇦', 'RE': '🇷🇪', 'RO': '🇷🇴', 'RU': '🇷🇺', 'RW': '🇷🇼', 'SH': '🇸🇭', 'KN': '🇰🇳',
    'LC': '🇱🇨', 'PM': '🇵🇲', 'VC': '🇻🇨', 'WS': '🇼🇸', 'SM': '🇸🇲', 'ST': '🇲🇱', 'SA': '🇸🇦',
    'SN': '🇸🇳', 'RS': '🇷🇸', 'SC': '🇸🇨', 'SL': '🇸🇱', 'SG': '🇸🇬', 'SX': '🇸🇽', 'SK': '🇸🇰',
    'SI': '🇸🇮', 'SB': '🇸🇧', 'SO': '🇸🇴', 'ZA': '🇿🇦', 'SS': '🇸🇸', 'ES': '🇪🇸', 'LK': '🇱🇰', 
    'SD': '🇸🇩', 'SR': '🇸🇷', 'SZ': '🇸🇿', 'SE': '🇸🇪', 'SG': '🇸🇬',
'SH': '🇸🇭', 'SI': '🇸🇮', 'SJ': '🇯🇲', 'SK': '🇸🇰', 'SL': '🇸🇱', 'SM': '🇸🇲', 'SN': '🇸🇳',
'SO': '🇸🇴', 'SR': '🇸🇷', 'SS': '🇸🇸', 'ST': '🇲🇱', 'SV': '🇸🇻', 'SX': '🇸🇽', 'SY': '🇸🇾',
'SZ': '🇸🇿', 'TC': '🇹🇨', 'TD': '🇹🇩', 'TF': '🇹🇫', 'TG': '🇹🇬', 'TH': '🇹🇭', 'TJ': '🇹🇯',
'TK': '🇹🇰', 'TL': '🇹🇱', 'TM': '🇹🇲', 'TN': '🇹🇳', 'TO': '🇹🇴', 'TR': '🇹🇷', 'TT': '🇹🇹',
'TV': '🇹🇻', 'TZ': '🇹🇿', 'UA': '🇺🇦', 'UG': '🇺🇬', 'UM': '🇺🇲', 'US': '🇺🇸', 'UY': '🇺🇾',
'UZ': '🇺🇿', 'VA': '🇻🇦', 'VC': '🇻🇨', 'VE': '🇻🇪', 'VN': '🇻🇳', 'VU': '🇻🇺', 'WF': '🇼🇫',
'WS': '🇼🇸', 'YE': '🇾🇪', 'YT': '🇲🇾', 'ZA': '🇿🇦', 'ZM': '🇿🇲', 'ZW': '🇿🇼'
}


# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Цветовая палитра для вывода
class Colors:
    DATE_TIME = Fore.CYAN
    IP_LINE = Fore.YELLOW
    RESULT = Fore.GREEN
    WARNING = Fore.MAGENTA
    ERROR = Fore.RED
    RESET = Style.RESET_ALL

# Создаем блокировку для синхронизации записи в файл
file_lock = asyncio.Lock()
# Создаем семафор для ограничения количества одновременных запросов
semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)

async def fetch_ip_info(session: ClientSession, ip: str) -> dict:
    """
    Запрашивает информацию о IP-адресе из API ipinfo.io.

    :param session: Объект aiohttp.ClientSession для выполнения запросов.
    :param ip: IP-адрес для запроса информации.
    :return: JSON объект с информацией о IP или None в случае ошибки.
    """
    try:
        async with semaphore:  # Ограничиваем количество одновременных запросов
            async with session.get(API_URL.format(ip), timeout=ClientTimeout(total=TIMEOUT)) as response:
                status = response.status
                if status == 429:
                    logging.error(f"{Colors.ERROR}Rate limit exceeded for IP {ip}.{Colors.RESET}")
                    return None
                elif status != 200:
                    logging.error(f"{Colors.ERROR}Unexpected HTTP status {status} for IP {ip}. Response text: {await response.text()}{Colors.RESET}")
                    return None
                return await response.json()
    except aiohttp.ClientResponseError as e:
        logging.error(f"{Colors.ERROR}HTTP error fetching IP info for {ip}: {e}{Colors.RESET}")
    except aiohttp.ClientConnectorError as e:
        logging.error(f"{Colors.ERROR}Connection error fetching IP info for {ip}: {e}{Colors.RESET}")
    except asyncio.TimeoutError:
        logging.error(f"{Colors.ERROR}Timeout error fetching IP info for {ip}{Colors.RESET}")
    except aiohttp.ClientError as e:
        logging.error(f"{Colors.ERROR}Client error fetching IP info for {ip}: {e}{Colors.RESET}")
    except Exception as e:
        logging.error(f"{Colors.ERROR}Unexpected error fetching IP info for {ip}: {e}{Colors.RESET}")
    return None

def get_country_flag(country_code: str) -> str:
    """
    Получает флаг страны по коду страны.

    :param country_code: Код страны (например, 'US').
    :return: Unicode флаг страны или пустая строка, если флаг не найден.
    """
    return FLAGS.get(country_code, '')

async def process_line(session: ClientSession, line: str) -> str:
    """
    Обрабатывает одну строку из входного файла.

    :param session: Объект aiohttp.ClientSession для выполнения запросов.
    :param line: Строка из входного файла, содержащая IP:порт;логин;пароль.
    :return: Строка с результатами обработки или None в случае ошибки.
    """
    try:
        parts = line.strip().split(';')
        if len(parts) != 3:
            logging.warning(f"{Colors.WARNING}Invalid line format: {line.strip()}{Colors.RESET}")
            return None

        ip_port, login, password = parts
        ip = ip_port.split(':')[0]  # Извлекаем только IP-адрес

        ip_info = await fetch_ip_info(session, ip)
        if not ip_info:
            return None

        country_code = ip_info.get('country', '')
        city = ip_info.get('city', '')
        org = ip_info.get('org', '')

        country_flag = get_country_flag(country_code)
        result = f"{Colors.IP_LINE}{line.strip()} | {country_flag} | {country_code} | {city} | {org}{Colors.RESET}"
        print(f"{Colors.RESULT}{result}{Colors.RESET}")  # Цветной вывод результата

        # Запись в файл с использованием блокировки
        async with file_lock:
            with open(OUTPUT_FILE, "a") as file:
                file.write(result + "\n")
                
        return result

    except IndexError:
        logging.error(f"{Colors.WARNING}Index error while processing line '{line.strip()}'{Colors.RESET}")
    except ValueError:
        logging.error(f"{Colors.WARNING}Value error while processing line '{line.strip()}'{Colors.RESET}")
    except Exception as e:
        logging.error(f"{Colors.ERROR}Error processing line '{line.strip()}': {e}{Colors.RESET}")
    return None

async def process_file(input_file: str):
    """
    Асинхронно читает строки из входного файла и обрабатывает их.

    :param input_file: Путь к входному файлу.
    """
    queue = asyncio.Queue()
    async with aiohttp.ClientSession() as session:
        # Чтение файла и добавление строк в очередь
        try:
            with open(input_file, 'r') as file:
                for line in file:
                    await queue.put(line)
        except FileNotFoundError:
            logging.error(f"{Colors.ERROR}Input file {input_file} not found.{Colors.RESET}")
            return
        except IOError as e:
            logging.error(f"{Colors.ERROR}Error reading input file {input_file}: {e}{Colors.RESET}")
            return
        except Exception as e:
            logging.error(f"{Colors.ERROR}Unexpected error reading input file {input_file}: {e}{Colors.RESET}")
            return

        async def worker():
            """
            Работник, который обрабатывает строки из очереди.
            """
            while True:
                line = await queue.get()
                if line is None:
                    break
                await process_line(session, line)
                queue.task_done()

        # Создаем рабочие задачи
        workers = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENT_REQUESTS)]

        try:
            # Ожидаем завершения обработки всех задач
            await queue.join()
        except asyncio.CancelledError:
            logging.error(f"{Colors.ERROR}Processing was cancelled.{Colors.RESET}")

        # Останавливаем рабочих
        for _ in range(MAX_CONCURRENT_REQUESTS):
            await queue.put(None)
        await asyncio.gather(*workers)

def signal_handler(signum, frame):
    """
    Обработчик сигналов для корректного завершения работы при получении сигнала завершения.

    :param signum: Номер сигнала.
    :param frame: Текущий стек вызовов.
    """
    print(f"{Colors.DATE_TIME}Received signal {signum}. Exiting...{Colors.RESET}")
    # Останавливаем цикл событий
    asyncio.get_event_loop().stop()

def main(input_file: str):
    """
    Основная функция для запуска обработки файла.

    :param input_file: Путь к входному файлу.
    """
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(process_file(input_file))
    except KeyboardInterrupt:
        print(f"{Colors.ERROR}Process interrupted by user{Colors.RESET}")
    finally:
        # Закрытие цикла событий и обработка всех оставшихся задач
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Ожидание завершения всех задач
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

if __name__ == "__main__":
    # Запуск скрипта
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = INPUT_FILE
    main(input_file)