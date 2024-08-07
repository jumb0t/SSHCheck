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

# Цветовая подсветка вывода в консоль
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    CRITICAL = '\033[41m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    PURPLE = '\033[95m'
    ORANGE = '\033[33m'
    DARK_ORANGE = '\033[38;5;208m'
    INFO = '\033[96m'  # Добавлено для использования в логах

print_lock = threading.Lock()

class CustomFormatter(logging.Formatter):
    """Класс для добавления цветной подсветки времени и уровня логов."""
    def format(self, record):
        levelname = record.levelname
        message = record.getMessage()
        asctime = self.formatTime(record, self.datefmt)

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
        
        asctime_color = f"{Colors.PURPLE}{asctime}{Colors.ENDC}"
        ip_address_pattern = re.compile(r'\d+\.\d+\.\d+\.\d+')
        message_color = ip_address_pattern.sub(lambda match: f"{Colors.ORANGE}{match.group(0)}{Colors.ENDC}", message)
        message_color = f"{Colors.DARK_ORANGE}{message_color}{Colors.ENDC}"

        formatted_message = f"{asctime_color} - {levelname_color} - {message_color}"

        return formatted_message

def setup_logging():
    """Настроить логирование в разные файлы по уровням и консоль."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Создание обработчиков для разных уровней логов
    handlers = {
        logging.DEBUG: 'debug.log',
        logging.INFO: 'info.log',
        logging.WARNING: 'warning.log',
        logging.ERROR: 'error.log',
        logging.CRITICAL: 'critical.log'
    }

    formatter = CustomFormatter()

    # Добавление консольного обработчика
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    for level, filename in handlers.items():
        file_handler = logging.FileHandler(filename)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)

def load_config(file_path='config.json'):
    """Загрузить конфигурацию из JSON-файла."""
    with open(file_path, 'r') as file:
        return json.load(file)

async def check_ssh_credentials(host, port, username, password, config, success_file):
    """Проверить SSH учетные данные и записать успешные попытки в файл."""
    result = {
        'host': host,
        'port': port,
        'username': username,
        'status': 'Failed',
        'message': ''
    }
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh_config = config['ssh']
    timeout = ssh_config.get('timeout', 5)
    max_retries = ssh_config.get('max_retries', 1)

    for attempt in range(max_retries):
        try:
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
            result['status'] = 'Success'
            result['message'] = 'Authentication successful'
            with print_lock:
                print(f"{Colors.OKGREEN}Success{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.info(f"Authentication successful for {host}:{port} with {username}")
            
            # Запись успешной попытки в файл
            async with aiofiles.open(success_file, 'a') as file:
                await file.write(f"{host}:{port};{username};{password}\n")
            client.close()
            break
        except paramiko.AuthenticationException:
            result['message'] = 'Authentication failed'
            with print_lock:
                print(f"{Colors.WARNING}Warning{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.warning(f"Authentication failed for {host}:{port} with {username}")
            break
        except paramiko.SSHException as e:
            result['message'] = f'SSHException: {e}'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"SSHException for {host}:{port} with {username} - {e}")
            await asyncio.sleep(2)  # Delay before retrying
        except socket.timeout:
            result['message'] = 'Connection timed out'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"Connection timed out for {host}:{port} with {username}")
            await asyncio.sleep(2)  # Delay before retrying
        except socket.error as e:
            result['message'] = f'Socket error: {e}'
            with print_lock:
                print(f"{Colors.ERROR}Error{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.error(f"Socket error for {host}:{port} with {username} - {e}")
            await asyncio.sleep(2)  # Delay before retrying
        except Exception as e:
            result['message'] = f'Unknown error: {e}'
            with print_lock:
                print(f"{Colors.CRITICAL}Critical{Colors.ENDC} - {host}:{port} - {username} - {result['message']}")
            logging.critical(f"Unknown error for {host}:{port} with {username} - {e}")
            break
    
    return result

async def load_credentials(file_path):
    """Загрузить учетные данные из файла."""
    credentials = []
    try:
        async with aiofiles.open(file_path, 'r') as file:
            async for line in file:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split('|')[0].strip()
                    if ';' in parts:
                        host_port, username, password = parts.split(';')
                        try:
                            host, port = host_port.split(':')
                            port = int(port)
                            if not (0 <= port <= 65535):
                                raise ValueError("Invalid port number")
                            # Валидация IP-адреса
                            socket.inet_aton(host)
                            credentials.append((host, port, username, password))
                        except ValueError:
                            with print_lock:
                                print(f"{Colors.WARNING}Warning{Colors.ENDC} - Неверный формат строки: {line}")
                            logging.warning(f"Неверный формат строки: {line}")
                    else:
                        with print_lock:
                            print(f"{Colors.WARNING}Warning{Colors.ENDC} - Неверный формат строки: {line}")
                        logging.warning(f"Неверный формат строки: {line}")
    except FileNotFoundError:
        with print_lock:
            print(f"{Colors.ERROR}Error{Colors.ENDC} - Файл не найден: {file_path}")
        logging.error(f"Файл не найден: {file_path}")
    except Exception as e:
        with print_lock:
            print(f"{Colors.ERROR}Error{Colors.ENDC} - Ошибка чтения файла: {e}")
        logging.error(f"Ошибка чтения файла {file_path}: {e}")
    return credentials

async def check_credentials_in_threads(credentials, max_workers, config, success_file):
    """Проверить учетные данные в потоках."""
    loop = asyncio.get_running_loop()
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = [
            loop.run_in_executor(
                executor, lambda cred: asyncio.run(check_ssh_credentials(*cred, config, success_file)), cred
            )
            for cred in credentials
        ]
        for result in await asyncio.gather(*tasks):
            results.append(result)
    
    return results

def print_statistics(results, start_time):
    """Вывести статистику работы скрипта."""
    total_ips = len(results)
    successful = sum(1 for r in results if r['status'] == 'Success')
    errors = sum(1 for r in results if r['status'] == 'Failed')
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\n{Colors.BOLD}Статистика выполнения:{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Успешные попытки: {successful}{Colors.ENDC}")
    print(f"{Colors.WARNING}Ошибки: {errors}{Colors.ENDC}")
    print(f"{Colors.INFO}Общее количество проверенных IP: {total_ips}{Colors.ENDC}")
    print(f"{Colors.INFO}Время выполнения: {duration:.2f} секунд{Colors.ENDC}")

async def main(credentials_file):
    setup_logging()
    config = load_config()
    
    start_time = time.time()
    success_file = config['ssh'].get('success_file', 'success.txt')
    max_workers = config['async'].get('max_workers', 10)

    if not os.path.isfile(credentials_file):
        print(f"{Colors.ERROR}Ошибка: Файл не найден: {credentials_file}{Colors.ENDC}")
        sys.exit(1)

    credentials = await load_credentials(credentials_file)
    if not credentials:
        print(f"{Colors.ERROR}Ошибка: Нет учетных данных для проверки.{Colors.ENDC}")
        sys.exit(1)

    results = await check_credentials_in_threads(credentials, max_workers, config, success_file)
    
    # Вывод статистики
    print_statistics(results, start_time)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Использование: {sys.argv[0]} <путь_к_файлу_учетных_данных>")
        sys.exit(1)

    credentials_file = sys.argv[1]
    try:
        asyncio.run(main(credentials_file))
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Прерывание выполнения пользователем.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"{Colors.CRITICAL}Ошибка: {e}{Colors.ENDC}")
        logging.critical(f"Ошибка: {e}")
        sys.exit(1)