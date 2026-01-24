import socket
import sys
import os
import threading
import time
import json
import logging
import logging.handlers
import bisect
from datetime import datetime, timedelta

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        "debug": ("[python code]", "Run python code to debug", {}),
        "restart": ("", "Restart server", {}),
        "exit": ("", "Shutdown server", {})
    }

    @staticmethod
    def output_command_helper(command):
        if command not in HelpingManager.__COMMANDS:
            print(f"Command '{command}' not found")
            return
        des = HelpingManager.__COMMANDS[command]
        print('-', command, des[0], '-', f"|{des[1]}|")
        for option, opdes in des[2].items():
            print('   ', option, '-', f"|{opdes}|")

    @staticmethod
    def output_all_command_helper():
        print("Controler commands:")
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
        self.clients = {}  # Key: identifier, Value: (socket, address)
        self.nicknames = {}  # Key: identifier, Value: nickname 
        self.client_history = {}  # Key: identifier, Value: (last_disconnect_time, last_address)
        self.scheduled_messages = []  # Item: command: ScheduledMessage
        self.banned_ipaddresses = []  # Item: ipaddress: str
        self.lock = threading.Lock()
        
        # Start message scheduler thread
        self.scheduler_thread = threading.Thread(target=self._check_scheduled_messages, daemon=True)
        self.scheduler_thread.start()
        
        # Load persistent data
        self.data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'controler_data.json')
        self._load_persistent_data()

    def _load_persistent_data(self):
        def _handle_scheduled_messages(data_mess: list) -> list:
            result: list[ScheduledMessage] = []
            now = datetime.now()
            for mess in data_mess:
                execute_time = datetime.strptime(mess["execute_time"], "%Y-%m-%d %H:%M:%S.%f")
                if (execute_time - now).total_seconds() > -5:
                    result.append(ScheduledMessage(mess["identifier"], mess["message"], execute_time))
            self.save_data()
            return result
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.nicknames = data.get('nicknames', {})
                    self.client_history = data.get('history', {})
                    self.banned_ipaddresses = data.get('banned-ipaddresses', [])
                    self.scheduled_messages = _handle_scheduled_messages(data.get('scheduled-messages', []))
                    logging.info(f"Loaded {len(self.banned_ipaddresses)} banned IP addresses and {len(self.nicknames)} nicknames and {len(self.client_history)} client records")
            else:
                logging.info("No existing data file, starting fresh")
                try:
                    with open(self.data_file, 'w') as f:
                        json.dump({
                            'nicknames': {},
                            'history': {},
                            'banned-ipaddresses': []
                        }, f)
                except Exception as e:
                    logging.error(f"Error writing to data file: {str(e)}")
                    logging.info("Starting server with empty data")
                    self.nicknames = {}
                    self.client_history = {}
                
        except Exception as e:
            logging.error(f"Error loading persistent data: {str(e)}")
            self.nicknames = {}
            self.client_history = {}
    
    def save_data(self):
        with open(self.data_file, 'w') as f:
            json.dump({
                'nicknames': self.nicknames,
                'history': self.client_history,
                'banned-ipaddresses': self.banned_ipaddresses,
                'scheduled-messages': [sche_mess.dict() for sche_mess in self.scheduled_messages]
            }, f)

    def add_client(self, identifier, client_socket, client_address):
        with self.lock:
            self.clients[identifier] = (client_socket, client_address)
            if identifier not in self.client_history:
                self.client_history[identifier] = ("", client_address)
            self.save_data()
            
    def kick_client(self, identifier):
        with self.lock:
            if identifier not in self.clients:
                print("Client not found")
                return
            client_socket, _ = self.clients[identifier]
            client_socket.close()
            del self.clients[identifier]
    
    def remove_client(self, identifier):
        with self.lock:
            if identifier in self.clients:
                client_socket, _ = self.clients[identifier]
                client_socket.close()
                del self.clients[identifier]
                # Record disconnect time before saving
                if identifier in self.client_history:
                    _, addr = self.client_history[identifier]
                    self.client_history[identifier] = (time.strftime("%Y-%m-%d %H:%M:%S"), addr)
                self.save_data()
    
    def remove_history_client(self, identifier):
        with self.lock:
            if identifier not in self.client_history:
                print("Client not found")
                return
            if identifier in self.clients:
                print("Client is online now, please kick it")
                return
            del self.client_history[identifier]
            if self.nicknames.get(identifier):
                del self.nicknames[identifier]
            self.save_data()
    
    def ban_ipaddress(self, ip_address):
        with self.lock:
            if ip_address not in self.banned_ipaddresses:
                self.banned_ipaddresses.append(ip_address)
                for identifier, (_, ipaddress) in self.clients.items():
                    if ipaddress[0] == ip_address:
                        self.kick_client(identifier)
                self.save_data()
                print("Ban IP successful")
            else:
                print("This IP address has already banned")
    
    def unban_ipaddress(self, ip_address):
        with self.lock:
            if ip_address in self.banned_ipaddresses:
                self.banned_ipaddresses.remove(ip_address)
                self.save_data()
                print("Unban IP address successful")
            else:
                print("This IP address not banned")
    
    def send_message(self, identifier, message):
        try:
            with self.lock:
                if identifier not in self.clients:
                    print("Client not found")
                    return
                client_socket, _ = self.clients[identifier]
            
            # Send outside of main lock
            client_socket.settimeout(5)
            try:
                client_socket.send(message.encode('utf-8'))
                with activity._lock:
                    if message.startswith('cmd '):
                        activity.command += 1
                return True
            except socket.timeout:
                logging.error(f"Send timeout for {identifier}")
            except Exception as e:
                logging.error(f"Send error for {identifier}: {str(e)}")
                self.remove_client(identifier)
            finally:
                client_socket.settimeout(None)
            
            return False
        except Exception as e:
            logging.error(f"\nUnexpected error in send_message: {str(e)}")
            return False
    
    def set_nickname(self, identifier, nickname):
        with self.lock:
            try:
                self.nicknames[identifier] = nickname
                self.save_data()
                return True
            except Exception as e:
                logging.error(f"\nError saving nickname: {str(e)}")
                return False
    
    def get_nickname(self, identifier):
        with self.lock:
            return self.nicknames.get(identifier, None)
    
    def get_identifier(self, identifier_or_nickname):
        with self.lock:
            for identifier, name in self.nicknames.items():
                if name == identifier_or_nickname:
                    return identifier
            return identifier_or_nickname
    
    def output_online_clients(self):
        online_clients = []
        with self.lock:
            online_clients = list(self.clients.items())
        print("Online clients:")
        if online_clients:
            for identifier, (_, address) in online_clients:
                nickname = self.get_nickname(identifier)
                display_name = f"{nickname} ({identifier})" if nickname else identifier
                print(f"  {display_name}, Address: {address[0]}:{address[1]}")
        else:
            print("  No client online") 
    
    def output_history_client(self):
        history_clients = []
        with self.lock:
            history_clients = list(self.client_history.items())
        print("History clients (offline):")
        have_history = False
        for identifier, (last_disconnect, address) in history_clients:
            if identifier not in self.clients:
                have_history = True
                nickname = self.get_nickname(identifier)
                display_name = f"{nickname} ({identifier})" if nickname else identifier
                last_disconnect = last_disconnect if last_disconnect else "Never"
                print(f"  {display_name}, Last online: {last_disconnect}, Address: {address[0]}:{address[1]}")
        if not have_history:
            print(f"  No history client")

    def output_banned_ipaddresses(self):
        print("Banned IPs")
        if self.banned_ipaddresses:
            for ipaddress in self.banned_ipaddresses:
                print(f"  - {ipaddress}")
        else:
            print("  No IP banned")
    
    def output_scheduled_messages(self):
        print("Scheduled messages:")
        with self.lock:
            scheduled_messages = self.scheduled_messages
        
        if scheduled_messages:
            for i, cmd in enumerate(scheduled_messages):
                nickname = self.get_nickname(cmd.identifier)
                display_name = f"{nickname} ({cmd.identifier})" if nickname else cmd.identifier
                print(f"  [{i+1}] {display_name}, Message: {cmd.message}, Send time: {cmd.execute_time}")
        else:
            print("  No scheduled messages")
    
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
                if self.send_message(scheduling_message.identifier, scheduling_message.message):
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
            print(e)
            return False

    def remove_scheduled_message(self, sche_mess_id: int):
        try:
            with self.lock:
                del self.scheduled_messages[sche_mess_id-1]
        except IndexError:
            print("Id out of range")

class activity:
    _lock = threading.Lock()
    command = 0

def handle_client(client_socket: socket.socket, client_address, client_manager: ClientManager):
    verified = False
    if client_address[0] in client_manager.banned_ipaddresses:
        client_socket.close()
        return
    try:
        # First receive client identifier
        client_socket.settimeout(5)
        try:
            data = client_socket.recv(128)
        except socket.timeout:
            client_socket.close()
            return
        except:
            client_socket.close()
            return

        if not data:
            return
        try:
            identifier = data.decode('utf-8')
        except UnicodeDecodeError:
            client_socket.close()
            return
        if not identifier.startswith("IDENTIFIER:"):
            client_socket.close()
            return
        
        identifier = identifier[11:]
        if len(identifier) != 16 or not all(c in '0123456789ABCDEF' for c in identifier):
            client_socket.close()
            return
        
        verified = True
        client_manager.add_client(identifier, client_socket, client_address)

        client_socket.settimeout(30)
        while True:
            try:
                data = client_socket.recv(65536)
                if not data:
                    break
                    
                try:
                    message = data.decode('utf-8')
                except UnicodeDecodeError:
                    client_socket.close()
                    return
                    
                if message == "HEARTBEAT":
                    client_socket.send("HEARTBEAT_RESPONSE".encode('utf-8'))
                    
                elif message == "HEARTBEAT_RESPONSE":
                    pass

                elif message.startswith("CMDRES:"):
                    with activity._lock:
                        if activity.command:
                            logging.info(f"Command result from {client_address}")
                            print(message[7:])
                            activity.command -= 1
                    
                elif message.startswith("CMDERR:"):
                    with activity._lock:
                        if activity.command:
                            logging.warning(f"Command error from {client_address}")
                            print(message[7:])
                            activity.command -= 1

                
            except socket.timeout:
                # 发送心跳检测
                try:
                    client_socket.send("HEARTBEAT".encode('utf-8'))
                except:
                    break
                    
    except:
        pass
    finally:
        if verified:
            client_manager.remove_client(identifier)

def server_input(client_manager: ClientManager):
    while True:
        try:
            cmd = input("> ")
            parts = cmd.split()

            if not parts:
                continue

            if parts[0] == "?":
                HelpingManager.output_all_command_helper()
            elif cmd.startswith("help"):
                if parts == ["help"]:
                    print('Use "help [command]" or "?" for help')
                    continue
                if len(parts) > 1:
                    command = parts[1]
                    if command == '-a':
                        HelpingManager.output_all_command_helper()
                    else:
                        HelpingManager.output_command_helper(command)
                else:
                    print("Invaild")
                    continue
            elif parts[0] == "now":
                print(datetime.now())
            elif cmd.startswith("send "):
                _, identifier_or_nickname, *message = cmd.split(' ', 2)
                message = message[0] if message else ""
                
                # Check if identifier_or_nickname is a nickname
                identifier = client_manager.get_identifier(identifier_or_nickname)
                client_manager.send_message(identifier, message)
            
            elif cmd.startswith("sche "):
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
                            continue
                        except IndexError:
                            raise ValueError("Invalid message format")
                    except IndexError:
                        raise ValueError("Invalid message format")

                    if execute_time < datetime.now():
                        logging.error("Scheduled time must be in the future")
                        continue

                    # Check if identifier_or_nickname is a nickname
                    identifier = client_manager.get_identifier(identifier_or_nickname)
                    if client_manager.schedule_message(identifier, message, execute_time):
                        logging.info(f"Message scheduled for {identifier_or_nickname} at {execute_time}: {message}")
                    else:
                        logging.error("Failed to schedule message")
                except Exception as e:
                    logging.error(f"Invalid schedule message: {str(e)}")

            elif cmd.startswith("rmsche "):
                try:
                    sche_mess_id = int(parts[1])
                except IndexError:
                    print("Invaild")
                    continue
                except ValueError:
                    print("Id is not a number")
                    continue
                
                client_manager.remove_scheduled_message(sche_mess_id)

            elif cmd.startswith("nkname "):
                identifier, *nickname = parts[1:]
                nickname = nickname[0] if nickname else ""
                if client_manager.set_nickname(identifier, nickname):
                    print(f"Nickname set for {identifier}")
                else:
                    print(f"Client {identifier} not found")
            elif cmd.startswith("kick "):
                identifier_or_nickname = parts[1]
                identifier = client_manager.get_identifier(identifier_or_nickname)
                try:
                    client_manager.kick_client(identifier)
                    print(f"Kick {identifier_or_nickname} successful")
                except Exception as e:
                    logging.error(f"Unkown error\n{str(e)}")
            elif cmd.startswith("ban "):
                ipaddress = parts[1]
                client_manager.ban_ipaddress(ipaddress)
            elif cmd.startswith("unban "):
                ipaddress = parts[1]
                client_manager.unban_ipaddress(ipaddress)
            elif cmd.startswith("rm "):
                _, identifier_or_nickname = cmd.split(' ', 2)
                identifier = client_manager.get_identifier(identifier_or_nickname)
                client_manager.remove_history_client(identifier)
                
            elif cmd.startswith("ls"):
                # Get snapshots to minimize lock time
                if len(parts) == 1:
                    client_manager.output_online_clients()
                    print()
                    client_manager.output_history_client()
                elif parts[1] == '-a':
                    client_manager.output_online_clients()
                    print()
                    client_manager.output_history_client()
                    print()
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
                    print("Unknow option:", parts[1])
            
            elif parts[0] == "save":
                logging.info("Saving data...")
                try:
                    with client_manager.lock:
                        client_manager.save_data()
                    logging.info("Save server data successfully")
                except Exception as e:
                    logging.error(f"Error while saving data: {str(e)}")

            # DEBUG
            elif cmd.startswith("debug "):
                code = cmd[6:]
                exec(code)

            elif parts[0] == "restart":
                logging.info("Restarting server...")
                python = sys.executable
                os.execl(python, python, *sys.argv)

            elif parts[0] == "exit":
                logging.info("Shutting down server...")
                # 通知所有线程退出
                os._exit(0)  # 强制退出所有线程

            else:
                print("Invaild")
           	
                
        except Exception as e:
            logging.error(f"Input error: {e}")

def start_server(host='0.0.0.0', port=30003):
    client_manager = ClientManager()
    
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(5)
        logging.info(f"Server started on {host}:{port}")
        
        # 启动服务端输入线程
        input_thread = threading.Thread(target=server_input, args=(client_manager,), daemon=True)
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
                print("\nCought Ctrl+C")
                print("Type 'exit' to quit")
                
    except Exception as e:
        logging.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_server()
