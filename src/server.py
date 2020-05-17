import os
import sys
import threading
import socket


HOST_NAME = socket.gethostname()
PORT = 21
CWD = os.getenv('HOME')

DEFAULT_USERS = {
    'test_user': '4247'
}


class FTPServer(threading.Thread):
    def __init__(self, client_socket, address):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.address = address
        self.commands = {
            'USER': self.USER,
            'PASS': self.PASS
        }
        self.cwd = CWD
        self.user = None
        self.password = None
        self.authenticated = None

    def run(self):
        while True:
            data = self.client_socket.recv(1024).strip()

            cmd = data.decode('utf-8')
            if not cmd:
                break

            print('Received:', cmd)

            try:
                cmd, arg = cmd[:4].strip().upper(), cmd[4:].strip() or None

                self.commands[cmd](arg)
            except KeyError:
                self.send_msg('500 Syntax error, command unrecognized\r\n')

    def USER(self, user):
        print('USER', user)
        if not user:
            self.send_msg('501 Syntax error in parameters or arguments.\r\n')
        elif user in DEFAULT_USERS:
            self.send_msg(f'331 User {user} OK. Password required\r\n')
            self.user = user

    def PASS(self, password):
        if not password:
            self.send_msg('501 Syntax error in parameters or arguments.\r\n')
        elif not self.user:
            self.send_msg('503 Bad sequence of commands.\r\n')
        elif DEFAULT_USERS[self.user] != password:
            print('pass', password)
            self.send_msg('530 Not logged in.\r\n')
            self.close_connection()
        else:
            self.send_msg(f'230 User {self.user} logged in/\r\n')
            self.password = password
            self.authenticated = True

    def PWD(self, cmd):
        self.send_msg(f'257 "{self.cwd}"')

    def send_msg(self, msg):
        self.client_socket.send(msg.encode('utf-8'))

    def close_connection(self):
        print(f'Closed connection with {self.address}')
        self.client_socket.close()
        sys.exit()


def listen():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST_NAME, PORT))
        s.listen(5)

        print(f'Listen on {s.getsockname()}')

        while True:
            client_socket, address = s.accept()
            ftp_server = FTPServer(client_socket, address)
            ftp_server.start()
            print('Accept', f'Created connection with {address}')


if __name__ == '__main__':
    print('Server started')
    print('Enter q to stop the server')

    listener_thread = threading.Thread(target=listen, daemon=True)
    listener_thread.start()

    while input().strip().lower() != 'q':
        pass
    else:
        print('Server stopped')
        sys.exit()
