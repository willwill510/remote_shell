# Features

### Custom protocol using message types
A custom protocol is used to send and recive messages which includes type, length, and the base64 encoded message itself.

### Timouts and retrys
The client will timeout commands in order to avoid infinite hanging.

### Persistant reconnection
The client will try to reconnect if unexpected error are encountered.

### Remotely command clients
The server can run any command which does not need elevated privileges.

### Multiple clients
The server can handle many clients simultaneously with custom individual labeling.

### File get & putting
The server can get files from the client aswell as putting files into the client.

### Easily modable
Adding custom commands is easy, just add a new type to use and add the logic to the mainloop of both server and client.
