import socket
import sys
import os
import threading
import time
import json
import errno
import bisect
from datetime import datetime, timedelta

class Logger:
    __get_time = lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
    def __init__(self, sock:socket.socket=None):
        self.sock = sock
        self.__lock = threading.Lock()

    def set_sock(self, client_socket: socket.socket):
        with self.__lock:
            self.sock = client_socket

    def __sender(self, mess: str):
        if self.sock: self.sock.send((mess+'\n').encode('utf-8'))
        print(mess)

    def rint(self, mess: str = ''):
        self.__sender(mess)
    
    def info(self, mess: str):
        message = Logger.__get_time() + ' - INFO - ' + mess
        self.__sender(message)
    
    def warning(self, mess: str):
        message = Logger.__get_time() + ' - WARNING - ' + mess
        self.__sender(message)
    
    def error(self, mess: str):
        message = Logger.__get_time() + ' - ERROR - ' + mess
        self.__sender(message)

logging = Logger()

class HelpingManager:
    __COMMANDS = {
        "?": ("", "Show help text", {}),
        "help": ("[command]", "Show help text about this command", {"-a": "Show whole help infomation"}),
        "now": ("", "Show now time", {}),
        "ls": ("", "List clients", {"-o": "List online clients", "-h": "List history clients", "-b": "List banned IP addresses", "-s": "List scheduled command","-a": "List all"}),
        "send": ("[client] [message]", "Send message to client", {}),
        "sche": ("[client] [date] [time]", "Schedule message execution", {}),
        "rmsche": ("[id](using ls -s to show)", "Remove scheduled message execution", {}),
        "nkname": ("[identifier] [nickname]", "Set nickname for client", {}),
        "kick": ("[client]", "Kick an online client", {}),
        "ban": ("[IPaddress]", "Ban an IP address", {}),
        "unban": ("[IPaddress]","Unban an IP address", {}),
        "rm": ("[client]", "Remove client in history clients", {}),
        "save": ("", "Save server data to controler_data.json", {}),
        "kapi": ("", "Turn on/off api connection allow", {}),
        "debug": ("[python code]", "Run python code to debug", {}),
        "restart": ("", "Restart server", {}),
        "exit": ("", "Shutdown server", {})
    }

    @staticmethod
    def output_command_helper(command):
        if command not in HelpingManager.__COMMANDS:
            logging.rint(f"Command '{command}' not found")
            return
        des = HelpingManager.__COMMANDS[command]
        logging.rint(f'- {command} {des[0]} - |{des[1]}|')
        for option, opdes in des[2].items():
            logging.rint(f"    {option} - |{opdes}|")

    @staticmethod
    def output_all_command_helper():
        logging.rint("Controler commands:")
        for cmd in HelpingManager.__COMMANDS:
            HelpingManager.output_command_helper(cmd)

class ScheduledMessage:
    def __init__(self, identifier: str, message: str, execute_time: datetime):
        self.identifier: str = identifier
        self.message: str = message
        self.execute_time: datetime = execute_time

    def __lt__(self, other):
        if not isinstance(other, ScheduledMessage):
            return NotImplemented
        return self.execute_time < other.execute_time

    def dict(self):
        return {"identifier": self.identifier, "message": self.message, "execute_time": self.execute_time.__str__()}

class ClientManager:
    def __init__(self):
        # Key: identifier, Value: socket
        self.clients = {}
        
        # Key: identifier, Value: nickname 
        self.nicknames = {}

        # Key: identifier, Value: (last_disconnect_time, last_address)
        self.client_history = {}

        # Item: command: ScheduledMessage
        self.scheduled_messages = []  

        # Item: ipaddress: str
        self.banned_ipaddresses = []  

        # Locker
        self.lock = threading.Lock()
        
        # Load persistent data
        self._data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'controler_data.json')
        self._load_persistent_data()
        
        # Start message scheduler thread
        self.scheduler_thread = threading.Thread(target=self._check_scheduled_messages, daemon=True)
        self.scheduler_thread.start()

    def _load_persistent_data(self):
        try:
            os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
            if os.path.exists(self._data_file):
                with open(self._data_file, 'r') as f:
                    data = json.load(f)
                    now = datetime.now()
                    self.nicknames = data.get('nicknames', {})
                    self.client_history = data.get('history', {})
                    self.banned_ipaddresses = data.get('banned-ipaddresses', [])

                    temp_messages = data.get('scheduled-messages', [])
                    for mess in temp_messages:
                        execute_time = datetime.strptime(mess["execute_time"], "%Y-%m-%d %H:%M:%S.%f")
                        if (execute_time - now).total_seconds() > -5:
                            self.scheduled_messages.append(ScheduledMessage(mess["identifier"], mess["message"], execute_time))
                    
                    logging.info(f"Loaded {len(self.banned_ipaddresses)} banned IP addresses and {len(self.nicknames)} nicknames and {len(self.client_history)} client records")
            else:
                logging.warn("No existing data file, starting fresh")
                try:
                    with open(self._data_file, 'w') as f:
                        json.dump({
                            'nicknames': {},
                            'history': {},
                            'banned-ipaddresses': [],
                            'scheduled-messages': []
                        }, f)
                except Exception as e:
                    logging.error(f"Error writing to data file: {str(e)}")
                    logging.info("Starting server with empty data")
                    self.nicknames = {}
                    self.client_history = {}
                    self.scheduled_messages = []
                
        except Exception as e:
            logging.error(f"Error loading persistent data: {str(e)}")
            self.nicknames = {}
            self.client_history = {}
            self.scheduled_messages = []
    
    def save_data(self):
        with open(self._data_file, 'w') as f:
            json.dump({
                'nicknames': self.nicknames,
                'history': self.client_history,
                'banned-ipaddresses': self.banned_ipaddresses,
                'scheduled-messages': [sche_mess.dict() for sche_mess in self.scheduled_messages]
            }, f)

    def add_client(self, identifier: str, client_socket: socket.socket):
        with self.lock:
            self.clients[identifier] = client_socket
            self.client_history[identifier] = (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), client_socket.getsockname())
            self.save_data()
            
    def close_client(self, identifier):
        client_socket = self.get_socket(identifier)
        if client_socket:
            client_socket.close()
            with self.lock:
                del self.clients[identifier]
                if identifier in self.client_history:
                    _, addr = self.client_history[identifier]
                    self.client_history[identifier] = (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), addr)
                self.save_data()
    
    def remove_history_client(self, identifier):
        with self.lock:
            if identifier not in self.client_history:
                logging.rint("Client not found")
                return
            if identifier in self.clients:
                logging.rint("Client is online now, please kick it")
                return
            del self.client_history[identifier]
            if self.nicknames.get(identifier):
                del self.nicknames[identifier]
            self.save_data()

    def send_message(self, identifier: str, message: bytes):
        try:
            client_socket: socket.socket = self.get_socket(identifier)
            if not client_socket:
                logging.rint("Client not found")
                return
            
            # Send outside of main lock
            client_socket.settimeout(10)
            try:
                client_socket.send(message)
                if message.startswith('cmd '.encode('utf-8')):
                    activity.add_command()
                return True
            except socket.timeout:
                logging.error(f"Send timeout for {identifier}")
            except Exception as e:
                logging.error(f"Send error for {identifier}: {str(e)}")
                self.close_client(identifier)
            finally:
                client_socket.settimeout(None)
            
            return False
        except Exception as e:
            logging.error(f"\nUnexpected error in send_message: {str(e)}")
            return False
    
    def ban_ipaddress(self, ip_address):
        with self.lock: self.banned_ipaddresses.append(ip_address); clients = self.clients
        if ip_address in self.banned_ipaddresses:
            logging.rint("This IP address has already banned")
            return
        for identifier, client_socket in clients.items():
            ipaddress = client_socket.getsockname()
            if ipaddress[0] == ip_address:
                self.close_client(identifier)
        with self.lock:
            self.save_data()
        logging.rint("Ban IP successful")
    
    def unban_ipaddress(self, ip_address):
        with self.lock:
            if ip_address in self.banned_ipaddresses:
                self.banned_ipaddresses.remove(ip_address)
                self.save_data()
                logging.rint("Unban IP address successful")
            else:
                logging.rint("This IP address not banned")
    
    def set_nickname(self, identifier: str, nickname: str):
        with self.lock:
            try:
                self.nicknames[identifier] = nickname
                self.save_data()
                return True
            except Exception as e:
                logging.error(f"\nError saving nickname: {str(e)}")
                return False

    def get_socket(self, identifier: str) -> socket.socket:
        with self.lock:
            return self.clients.get(identifier)

    def get_nickname(self, identifier: str) -> str:
        with self.lock:
            return self.nicknames.get(identifier)
    
    def get_identifier(self, identifier_or_nickname: str) -> str:
        with self.lock:
            nknames = self.nicknames.items()
        for identifier, name in nknames:
            if name == identifier_or_nickname:
                return identifier
        return identifier_or_nickname

    def get_name(self, identifier) -> str:
        nickname = self.get_nickname(identifier)
        return f'{nickname} ({identifier})' if nickname else identifier

    def output_online_clients(self):
        with self.lock:
            online_clients = list(self.clients.items())
        logging.rint("Online clients:")
        if online_clients:
            for identifier, client_socket in online_clients:
                address = client_socket.getsockname()
                display_name = self.get_name(identifier)
                logging.rint(f"  {display_name}, Address: {address[0]}:{address[1]}")
        else:
            logging.rint("  No client online") 
        logging.rint()
    
    def output_history_client(self):
        history_clients = []
        with self.lock:
            history_clients = list(self.client_history.items())
        logging.rint("History clients (offline):")
        have_history = False
        for identifier, (last_disconnect, address) in history_clients:
            if identifier not in self.clients:
                have_history = True
                display_name = self.get_name(identifier)
                logging.rint(f"  {display_name}, Last online: {last_disconnect}, Address: {address[0]}:{address[1]}")
        if not have_history:
            logging.rint(f"  No history client")
        logging.rint()

    def output_banned_ipaddresses(self):
        logging.rint("Banned IPs")
        if self.banned_ipaddresses:
            for ipaddress in self.banned_ipaddresses:
                logging.rint(f"  - {ipaddress}")
        else:
            logging.rint("  No IP banned")
        logging.rint()
    
    def output_scheduled_messages(self):
        logging.rint("Scheduled messages:")
        with self.lock:
            scheduled_messages = self.scheduled_messages
        
        if scheduled_messages:
            for i, cmd in enumerate(scheduled_messages):
                nickname = self.get_nickname(cmd.identifier)
                display_name = f"{nickname} ({cmd.identifier})" if nickname else cmd.identifier
                logging.rint(f"  [{i+1}] {display_name}, Message: {cmd.message}, Send time: {cmd.execute_time}")
        else:
            logging.rint("  No scheduled messages")
        logging.rint()
    
    def _check_scheduled_messages(self):
        while True:
            time.sleep(0.5)
            with self.lock:
                if not self.scheduled_messages:
                    continue
                now = datetime.now()
                changed = False
                while self.scheduled_messages:
                    if now >= self.scheduled_messages[0].execute_time:
                        threading.Thread(target=self.send_scheduled_message, args=(self.scheduled_messages[0],)).start()
                        del self.scheduled_messages[0]
                        changed = True
                    else: break
                if changed: self.save_data()

                    
    def send_scheduled_message(self, scheduling_message: ScheduledMessage):
        if scheduling_message.identifier not in self.clients:
            logging.error(f"Failed to send scheduled message - Client {scheduling_message.identifier} not online")
        else:
            for _ in range(3):
                if self.send_message(scheduling_message.identifier, scheduling_message.message.encode('utf-8')):
                    logging.info(f"Message {scheduling_message.message} for {scheduling_message.identifier} sent successfully")
                    break
            else:
                logging.error(f"Failed to send scheduled message for {scheduling_message.identifier}")


    def schedule_message(self, identifier: str, message, execute_time: datetime):
        try:
            sche_mess = ScheduledMessage(identifier, message, execute_time)
            with self.lock:
                # Insert sort
                position = bisect.bisect_right(self.scheduled_messages, sche_mess)
                self.scheduled_messages.insert(position, sche_mess)
            self.save_data()
            return True
        except Exception as e:
            logging.rint(str(e))
            return False

    def remove_scheduled_message(self, sche_mess_id: int):
        try:
            with self.lock:
                del self.scheduled_messages[sche_mess_id-1]
                self.save_data()
        except IndexError:
            logging.rint("Id out of range")

class activity:
    _lock = threading.Lock()
    command = 0
    def add_command():
        with activity._lock:
            activity.command += 1
    
    def reduce_command():
        if activity.check_command():
            with activity._lock:
                activity.command -= 1
        else: logging.error("Server Error: No command to reduce")
    
    def check_command():
        with activity._lock:
            return bool(activity. command)

def handle_client_message(identifier: str):
    while True:
        try:
            client_socket = client_manager.get_socket(identifier)
            if client_socket._closed: return
            data = client_socket.recv(65536)
            if not data: client_socket.close(); return
            try: message = data.decode('utf-8')
            except UnicodeDecodeError: client_manager.close_client(identifier); return
                
            if message == "HEARTBEAT":
                client_manager.send_message(identifier, 'HEARTBEAT_RESPONSE'.encode('utf-8'))
            
            elif message.startswith("CMDRES:"):
                if activity.check_command():
                    logging.info(f"Command result from {client_manager.get_name(identifier)}")
                    logging.rint(message[7:])
                    activity.reduce_command()
                
            elif message.startswith("CMDERR:"):
                if activity.check_command():
                    logging.warning(f"Command error from {client_manager.get_name(identifier)}")
                    logging.rint(message[7:])
                    activity.reduce_command()
            
            elif message == "HEARTBEAT_RESPONSE": pass

            else:
                client_manager.close_client(identifier)
                return

        except socket.timeout:
            try: client_socket.send("HEARTBEAT".encode('utf-8'))
            except: return
        except Exception as e: logging.error(f"In function handle_client_message: {str(e)}"); return

def handle_api_message(client_socket: socket.socket):
    global API_ALLOW
    while True:
        try:
            data = client_socket.recv(65536)
            command = data.decode('utf-8')
            print('Execute command from API:', command)
            try: handle_command(command)
            except: pass
        except UnicodeDecodeError: client_socket.close(); break
        except socket.timeout: client_socket.close(); break
        except: break

def handle_client(client_socket: socket.socket, client_address, client_manager: ClientManager):
    if client_address[0] in client_manager.banned_ipaddresses:
        client_socket.close()
        return
    try:
        # First receive client identifier
        client_socket.settimeout(10)
        try: data = client_socket.recv(27)
        except: client_socket.close(); return
        if not data: client_socket.close(); return

        # Decode the action
        try: action = data.decode('utf-8')
        except UnicodeDecodeError: client_socket.close(); return
        if action.startswith("IDENTIFIER:"):
            identifier = action[11:]
            if len(identifier) != 16 or not all(c in '0123456789ABCDEF' for c in identifier):
                client_socket.close()
                return
            
            client_manager.add_client(identifier, client_socket)
            client_socket.settimeout(30)

            # Client message handler
            handle_client_message(identifier)
                        
        elif action.startswith("API:"):
            global API_ALLOW
            if not API_ALLOW: client_socket.close(); return
            password = action[4:]
            if password != PASSWORD: client_socket.close(); return
            client_socket.settimeout(60)

            # API message handler
            logging.warning(f"API from {client_socket.getsockname()} interrupt")
            logging.set_sock(client_socket)
            handle_api_message(client_socket)
            logging.set_sock(None)
            logging.warning(f"API from {client_socket.getsockname()} disconnected")
        
        else: client_socket.close(); return
                
    except: pass

def handle_command(cmd: str):
    parts = cmd.split()
    if not parts: return

    if parts[0] == '?':
        HelpingManager.output_all_command_helper()

    elif parts[0] == 'help':
        if len(parts) == 1:
            logging.rint('Use "help [command]" for one command\'s help or "help -a" / "?" for whole help')
        else:
            command = parts[1]
            if command == '-a': HelpingManager.output_all_command_helper()
            else: HelpingManager.output_command_helper(command)

    elif parts[0] == 'now':
        logging.rint(str(datetime.now()))
        
    elif parts[0] == 'send':
        _, identifier_or_nickname, *message = cmd.split(' ', 2)
        message = message[0] if message else ""
        
        # Check if identifier_or_nickname is a nickname
        identifier = client_manager.get_identifier(identifier_or_nickname)
        client_manager.send_message(identifier, message.encode('utf-8'))
    
    elif parts[0] == 'sche':
        try:
            if len(parts) < 4:
                raise ValueError("Invalid message format")
            
            identifier_or_nickname = parts[1]
            try:
                delta_seconds = int(parts[2])
                message = ' '.join(parts[3:])
                execute_time = datetime.now() + timedelta(seconds=delta_seconds)
            except ValueError:
                try:
                    time_part = f"{parts[2]} {parts[3]}"
                    message = ' '.join(parts[4:])
                    execute_time = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    logging.error("Time format must be either minutes (number) or %Y-%m-%d %H:%M:%S")
                    return
                except IndexError:
                    raise ValueError("Invalid message format")
            except IndexError:
                raise ValueError("Invalid message format")

            if execute_time < datetime.now():
                logging.error("Scheduled time must be in the future")
                return

            # Check if identifier_or_nickname is a nickname
            identifier = client_manager.get_identifier(identifier_or_nickname)
            if client_manager.schedule_message(identifier, message, execute_time):
                logging.info(f"Message scheduled for {identifier_or_nickname} at {execute_time}: {message}")
            else:
                logging.error("Failed to schedule message")
        except Exception as e:
            logging.error(f"Invalid schedule message: {str(e)}")

    elif parts[0] == 'rmsche':
        try: sche_mess_id = int(parts[1])
        except IndexError: logging.rint("Invaild") ;return
        except ValueError:
            logging.rint("Id is not a number")
            return
        
        client_manager.remove_scheduled_message(sche_mess_id)
        logging.info("Remove Scheduled message successful")

    elif parts[0] == 'nkname':
        identifier, *nickname = parts[1:]
        nickname = nickname[0] if nickname else ""
        if client_manager.set_nickname(identifier, nickname):
            logging.rint(f"Nickname set for {identifier}")
        else:
            logging.rint(f"Client {identifier} not found")

    elif parts[0] == 'kick':
        identifier_or_nickname = parts[1]
        identifier = client_manager.get_identifier(identifier_or_nickname)
        client_manager.close_client(identifier)
        logging.rint(f"Kick {identifier_or_nickname} successfully")

    elif parts[0] == 'ban':
        ipaddress = parts[1]
        client_manager.ban_ipaddress(ipaddress)

    elif parts[0] == 'unban':
        ipaddress = parts[1]
        client_manager.unban_ipaddress(ipaddress)

    elif parts[0] == 'rm':
        _, identifier_or_nickname = cmd.split(' ', 2)
        identifier = client_manager.get_identifier(identifier_or_nickname)
        client_manager.remove_history_client(identifier)
        
    elif parts[0] == 'ls':
        # Get snapshots to minimize lock time
        if len(parts) == 1:
            client_manager.output_online_clients()
            client_manager.output_history_client()
        elif parts[1] == '-a':
            client_manager.output_online_clients()
            client_manager.output_history_client()
            client_manager.output_banned_ipaddresses()
        elif parts[1] == '-b':
            client_manager.output_banned_ipaddresses()
        elif parts[1] == '-o':
            client_manager.output_online_clients()
        elif parts[1] == '-h':
            client_manager.output_history_client()
        elif parts[1] == '-s':
            client_manager.output_scheduled_messages()
        else:
            logging.rint("Unknow option: " + parts[1])
    
    elif parts[0] == 'save':
        logging.info("Saving data...")
        try:
            with client_manager.lock:
                client_manager.save_data()
            logging.info("Save server data successfully")
        except Exception as e:
            logging.error(f"While saving data: {str(e)}")

    elif parts[0] == 'kapi':
        global API_ALLOW
        API_ALLOW = not API_ALLOW
        logging.info(f"API Allow set {API_ALLOW}")

    # DEBUG
    elif parts[0] == 'debug':
        code = cmd[6:]
        try: exec(code)
        except Exception as e:
            logging.error(f"Wrong debugging code: {str(e)}")

    elif parts[0] == 'restart':
        logging.info("Restarting server...")
        python = sys.executable
        os.execv(python, ['python'] + sys.argv)

    elif parts[0] == 'exit' or parts[0] == 'quit':
        logging.info("Saving data...")
        with client_manager.lock:
            client_manager.save_data()
        logging.info("Shutting down server...")
        os._exit(0)

    elif parts[0] == 'fquit':
        logging.info("Force quiting...")
        os._exit(0)

    else:
        logging.rint("Invaild")

def server_io():
    while True:
        try:
            command = input("> ")
            handle_command(command)
        except Exception as e:
            logging.error(f"Input error: {str(e)}")

def start_server(host='0.0.0.0', port=30003):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((host, port))
        server_socket.listen(5)
        logging.info(f"Server started on {host}:{port}")
        
        # 启动服务端输入线程
        input_thread = threading.Thread(target=server_io, daemon=True)
        input_thread.start()
        
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                if client_address[0] in client_manager.banned_ipaddresses:
                    client_socket.close()
                    continue
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, client_address, client_manager),
                    daemon=True
                )
                client_thread.start()
                
            except KeyboardInterrupt:
                logging.rint("\nCought Ctrl+C")
                logging.rint("Type 'exit' to quit")
    
    except OSError as e:
        # Error code on linux and windows
        if e.errno == errno.WSAEADDRINUSE or e.errno == errno.EADDRINUSE:
            logging.error(f"Port {port} has already in use")
        else:
            logging.error(f"Cannot bind: {e}")

    except Exception as e:
        logging.error(f"Server error: {e}")
    
    finally:
        sys.exit(0)

client_manager = ClientManager()
PASSWORD: str = 'frank666'
API_ALLOW = True

if __name__ == "__main__":
    start_server()
