from base64 import b64encode, b64decode
from threading import Thread
from os.path import exists
from socket import socket
from shlex import split
from time import sleep
from json import loads

# the target host and port to connect to
host = '0.0.0.0'
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

# higher level socket class
class Socket():

    def __init__(self, host, port, sock=None, type_max=4, length_max=8, label=None):
        self.host = host # host ip address
        self.port = port # port number
        self.sock = sock if sock else socket() # low-level socket object, creates a new socket by default
        self.type_max = type_max # max bytes in the type segement of the message header
        self.length_max = length_max # max bytes in the length segement of the message header
        self.label = label if label else port # the identifier of the socket, defaults to the port

    def send(self, type, data, timeout=None): # custom higher level send function
        self.sock.settimeout(timeout)
        
        compressed = b64encode(data) # compress the data
        header = type.to_bytes(self.type_max) + len(compressed).to_bytes(self.length_max) # create the header of the message consisting of the type and length

        self.sock.send(header + compressed) # send the header followed by the compressed content

    def recv(self, timeout=None): # custom higher level recv function
        self.sock.settimeout(timeout)

        type = int.from_bytes(self.sock.recv(self.type_max)) # recv type of message
        length = int.from_bytes(self.sock.recv(self.length_max)) # recv length of message
        compressed = b'' # create a string where the compressed message will be assembled
        
        # add to the message until the full length message has been assembled
        while len(compressed) < length:
            compressed += self.sock.recv(length-len(compressed))

        data = b64decode(compressed) # decompress the message
        return type, data
    
    def expect(self, expected, retrys=2, timeout=None): # function to try to recv a specific message type with retrys
        for _ in range(retrys + 1):
            type, data = self.recv(timeout)

            if type == expected:
                return data
            
        raise ValueError('Unexpected value!')

# socket class with server-specific variables and functions
class Server(Socket):

    def __init__(self, host, port, sock=None, type_max=4, length_max=8, label=None):
        super().__init__(host, port, sock, type_max, length_max, label)
        self.focus = None # currently focused client
        self.focus_cwd = None # focused client's current working directory
        self.clients = {} # variable for storing all connected clients
    
    def bind(self, backlog): # function to combine two initalizing function into one
        self.sock.bind((self.host, self.port))
        self.sock.listen(backlog)

    def accept(self, timeout=None, timeout_hds=4): # function to accept clients
        while True:
            self.sock.settimeout(timeout)

            try:
                accepted = self.sock.accept() # accept the low level socket object and address
                client = Socket(accepted[1][0], accepted[1][1], accepted[0]) # create a client object

                try:
                    client.label = client.expect(type_hds, timeout_hds).decode() # get the label from the client (also proves as a sort of authentication that the client is my client program)
                
                except (ValueError, TimeoutError, OverflowError, MemoryError): # if errors occur, restart loop and try again
                    client.sock.close()
                    continue
                
                if client.label in self.clients.keys(): # if there is a duplicate label use the new client's port instead (which is always unique)
                    client.label = str(client.port)

                self.clients[client.label] = client # add client to the list of connected clients
                return client
            
            except ConnectionError:
                continue

            except TimeoutError:
                return

    def broadcast(self, type, data, timeout=4): # function to send a message to all conected clients and handle disconnections.
        clients = self.clients.copy().values()

        for client in clients:
            try:
                client.send(type, data, timeout) # send message to each client

            except ConnectionError:
                self.clients.pop(client.label) # remove client if disconnected

            except TimeoutError:
                self.clients.pop(client.label).close() # disconnect client if response time is too slow

    def accept_thread(self): # passively accepts new connections in the background
        while True:
            self.accept()

    def ping_thread(self, interval=30): # passively pings all registered clients to check if they are connected
        while True:
            self.broadcast(type_png, b'keep-alive-ping')
            sleep(interval)

server = Server(host, port) # initalize server
server.bind(4) # bind to port and allow connections

print('Waiting for inital connection . . .')
server.focus = server.accept() # accept a first client
print(f'Connected to {server.focus.label}! ({server.focus.host}:{server.focus.port})')

# start threads
ping_thread = Thread(target=server.ping_thread)
accept_thread = Thread(target=server.accept_thread)

ping_thread.start()
accept_thread.start()

# mainloop
while True:
    try:
        server.focus.send(type_gcd, b'_') # request current working directory
        server.focus_cwd = server.focus.expect(type_gcd).decode() # update current working directory

    except ConnectionError:
        print('Focus disconnected!')

        if len(server.clients) <= 1:
            server.focus = list(server.clients.values())[0]
            print(f'Switched to {server.focus.label}')

        else:
            raise RuntimeError('No clients available to switch to, try restarting.')

    try:
        command = input(f'[{server.focus.label}] {server.focus_cwd}>> ') # get input from the user
        sliced = split(command) # deconstructs the command into different parts (command type and arguments)

    except ValueError: # catch any client error in input such as having an isolated "\"
        print('Syntax error in command.')
        continue

    if not sliced: # if the command is empty just restart loop
        continue

    elif sliced[0].lower() == 'clients': # command to see connected clients and switch focus
        try:
            new = sliced[1] # input is given in the form of the new focus's label

            if new in server.clients.keys(): # if the input is a actual client switch
                server.focus = server.clients[new]
                print(f'Client focus changed to {server.focus.label}!')
            
            else:
                print('Client not found!')

        except IndexError: # if no further input aside from "clients" is given print out focus and connected clients
            print(f'Current: {server.focus.label}')
            print(f'Clients: {', '.join(server.clients)}')

        continue

    elif sliced[0].lower() == 'label': # command to label the current focus with user input
        try:
            new = sliced[1] # check for input

        except IndexError:
            print('Invalid arguments!')
            continue # if no input is given tell user and restart loop
        
        for label, client in server.clients.items():
            if label == new: # check if the label is already being used on another client
                print('Label must be unique!')
                continue
        
        # switch out old label for new label
        server.clients[new] = server.clients.pop(server.focus.label)
        server.focus.label = new
        
        print('New label added!')
        continue # skip output since this command doesn't affect client

    elif sliced[0].lower() == 'cd': # command to change directory
        try:
            new_dir = sliced[1] # check for input
        
        except IndexError:
            print('Invalid arguments!')
            continue # if no input is given, restart loop

        server.focus.send(type_cwd, new_dir.encode()) # send user input

    elif sliced[0].lower() == 'get': # command for getting files from focus
        try:
            # check for input
            client_path = sliced[1]
            server_path = sliced[2]
        
        except IndexError:
            print('Invalid arguments!')
            continue # if no input is given, restart loop

        server.focus.send(type_get, client_path.encode()) # send user path input
        file_exists = int(server.focus.expect(type_rsp)) # client response of if it exists or not

        if file_exists: # if the file exists, get it
            make_file(server_path, server.focus.expect(type_cnt))

    elif sliced[0].lower() == 'put': # command for putting files onto focus
        try:
            # check for input
            server_path = sliced[1]
            client_path = sliced[2]
        
        except IndexError:
            print('Invalid arguments!')
            continue # if no input is given, restart loop

        if exists(server_path): # if file exists on this machine send the path then content
            server.focus.send(type_put, client_path.encode())
            server.focus.send(type_cnt, read_file(server_path))
        
        else: # if files doesn't exist then tell user and restart loop
            print('File not found!')
            continue
    
    else: # if command is not custom coded it is send to be run in the focus cmd
        server.focus.send(type_cmd, command.encode())

    output = loads(server.focus.expect(type_out)) # genaric exit code and output from all command involving the client
    print(f'[Exit: {output[0]}]\n{output[1]}')