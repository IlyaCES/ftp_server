import grp
import os
import pwd
import stat
import sys
import threading
import socket
import shutil
import time

HOST_NAME = socket.gethostname()
PORT = 8000
CWD = os.getenv('HOME')

DEFAULT_USERS = {
    'test_user': '4247'
}


class FTPServer(threading.Thread):
    def __init__(self, client_socket, address):
        threading.Thread.__init__(self, daemon=True)
        self.client_socket = client_socket
        self.server_socket = None
        self.data_socket = None
        self.address = address
        self.commands = {
            'USER': self.USER,
            'PASS': self.PASS,
            'PWD': self.PWD,
            'CDUP': self.CDUP,
            'CWD': self.CWD,
            'MKD': self.MKD,
            'SYST': self.SYST,
            'QUIT': self.QUIT,
            'DELE': self.DELE,
            'RMD': self.RMD,
            'RNFR': self.RNFR,
            'RNTO': self.RNTO,
            'PASV': self.PASV,
            'PORT': self.PORT,
            'LIST': self.LIST,
            'STOR': self.STOR,
            'TYPE': self.TYPE,
            'REST': self.REST,
            'RETR': self.RETR
        }
        self.cwd = CWD
        self.user = None
        self.password = None
        self.authenticated = False
        self.pasv_mode = False
        self.rnfr_file = None
        self.data_socket_address = None
        self.data_socket_port = None
        self.mode = 'A'
        self.pos = None
        self.rest = False

    def run(self):
        self.send_msg('220 Welcome.\r\n')

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

    def open_data_socket(self):
        try:
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.pasv_mode:
                self.data_socket, self.address = self.server_socket.accept()
            else:
                self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.data_socket.connect((self.data_socket_address, self.data_socket_port))
        except socket.error as err:
            print('open_data_socket error:', err)
            self.close_connection()

    def close_data_socket(self):
        try:
            self.data_socket.close()
            if self.pasv_mode:
                self.server_socket.close()
        except socket.error as err:
            print('close_data_socket error', err)
            self.close_connection()

    def USER(self, user):
        print('USER', user)
        if not user:
            self.send_msg('501 Syntax error in parameters or arguments.\r\n')
        elif user in DEFAULT_USERS:
            self.send_msg(f'331 User {user} OK. Password required\r\n')
            self.user = user

    def PASV(self, cmd):
        self.pasv_mode = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST_NAME, 0))
        self.server_socket.listen(5)
        address, port = self.server_socket.getsockname()
        self.send_msg('227 Entering Passive Mode (%s,%u,%u).\r\n' %
                         (','.join(address.split('.')), port >> 8 & 0xFF, port & 0xFF))

    def PORT(self, cmd):
        if self.pasv_mode:
            self.server_socket.close()
            self.pasv_mode = False
        print('PORT cmd:', cmd)
        l = cmd.split(',')
        self.data_socket_address = '.'.join(l[:4])
        self.data_socket_port = (int(l[4]) << 8) + int(l[5])
        self.send_msg('200 Get port.\r\n')

    def TYPE(self, type_arg):
        if type_arg not in ('I', 'A'):
            self.send_msg(f'504 type {type_arg} not supported')
            return
        self.mode = type_arg
        if self.mode == 'I':
            self.send_msg('200 Binary mode.\r\n')
        elif self.mode == 'A':
            self.send_msg('200 Ascii mode.\r\n')

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
        self.send_msg(f'257 "{self.cwd}".\r\n')

    def CWD(self, dirpath):
        path = os.path.join(self.cwd, dirpath)
        if os.path.exists(path) and os.path.isdir(path):
            self.cwd = path
            self.send_msg('250 CWD Command successful.\r\n')
        else:
            self.send_msg('550 CWD failed Directory not exists.\r\n')

    def CDUP(self, cmd):
        self.cwd = os.path.abspath(os.path.join(self.cwd, '..'))
        self.send_msg('200 Ok.\r\n')

    def MKD(self, dirname):
        if not self.authenticated:
            self.send_msg('530 User not logged in.\r\n')
        else:
            pathname = os.path.join(self.cwd, dirname)
            try:
                os.mkdir(pathname)
                self.send_msg('257 Directory created.\r\n')
            except OSError:
                self.send_msg(f'550 MKD failed Directory {pathname} already exists.\r\n')

    def RMD(self, dirname):
        if not self.authenticated:
            self.send_msg('530 User not logged in.\r\n')
            return

        path = os.path.join(self.cwd, dirname)
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
            self.send_msg('250 Directory deleted.\r\n')
        else:
            self.send_msg(f"550 RMD failed Directory {path} doesn't exist.\r\n")

    def RNFR(self, filename):
        path = os.path.join(self.cwd, filename)
        if os.path.exists(path):
            self.rnfr_file = path
            self.send_msg('350 RNFR accepted. Please supply new name for RNTO.\r\n')
        else:
            self.send_msg(f"550 RNFR failed File or Directory {path} doesn't exist")

    def RNTO(self, filename):
        if not self.rnfr_file:
            self.send_msg('503 RNTO failed File or Directory not specified.\r\n')
            return

        if not filename:
            self.send_msg(f'553 RNTO failed File name "{filename}" not allowed.\r\n')
            return

        os.rename(self.rnfr_file, os.path.join(self.cwd, filename))
        self.rnfr_file = None
        self.send_msg('250 Filed renamed.\r\n')

    def DELE(self, filename):
        if not self.authenticated:
            self.send_msg('530 User not logged in.\r\n')
            return

        path = os.path.join(self.cwd, filename)
        if os.path.exists(path) and os.path.isfile(path):
            os.remove(path)
            self.send_msg('250 File deleted.\r\n')
        else:
            self.send_msg(f"550 DELE failed File {path} doesn't exist.\r\n")

    def LIST(self, dirpath):
        if not self.authenticated:
            self.send_msg('530 User not logged in.\r\n')
            return

        if not dirpath:
            path = os.path.abspath(os.path.join(self.cwd, '.'))
        else:
            path = os.path.abspath(os.path.join(self.cwd, dirpath))

        if not os.path.exists(path):
            self.send_msg(f'550 LIST failed Path {path} not exists.\r\n')
        else:
            self.send_msg('150 Here is listing.\r\n')
            self.open_data_socket()
            if os.path.isdir(path):
                for file in os.listdir(path):
                    file_msg = self.get_file_property(os.path.join(path, file))
                    self.send_data(file_msg + '\r\n')
            else:
                file_msg = self.get_file_property(path)
                self.send_msg(file_msg + '\r\n')
            self.close_data_socket()
            self.send_msg('226 List done.\r\n')

    def STOR(self, filename):
        if not self.authenticated:
            self.send_msg('530 STOR failed User not logged in.\r\n')
            return

        path = os.path.join(self.cwd, filename)
        try:
            if self.mode == 'I':
                file = open(path, 'wb')
            else:
                file = open(path, 'w')
        except OSError as err:
            print('STOR error:', err)
            return

        self.send_msg('150 Opening data connection.\r\n')
        self.open_data_socket()
        while True:
            data = self.data_socket.recv(1024)
            if not data:
                break
            if self.mode == 'A':
                data = data.decode('ascii')
            file.write(data)
        file.close()
        self.close_data_socket()
        self.send_msg('226 Transfer completed.\r\n')

    def RETR(self, filename):
        path = os.path.join(self.cwd, filename)
        if filename and os.path.exists(path):
            try:
                if self.mode == 'I':
                    file = open(path, 'rb')
                else:
                    file = open(path, 'r')
            except OSError as err:
                print('RETR error:', err)
                return

            self.send_msg('150 Opening data connection.\r\n')
            if self.rest:
                file.seek(self.pos)
                self.rest = False

            self.open_data_socket()
            while True:
                data = file.read(1024)
                if not data:
                    break
                self.send_data(data)
            file.close()
            self.close_data_socket()
            self.send_msg('226 Transfer completed.\r\n')

    def REST(self, pos):
        self.pos = int(pos)
        self.rest = True
        self.send_msg('250 File position reseted.\r\n')

    def SYST(self, arg):
        self.send_msg(f'215 {sys.platform} type.\r\n')

    def QUIT(self, arg):
        self.send_msg('221 Goodbye.\r\n')
        self.close_connection()

    def send_msg(self, msg):
        self.client_socket.send(msg.encode('utf-8'))

    def send_data(self, data):
        self.data_socket.send(data.encode('utf-8'))

    def close_connection(self):
        print(f'Closed connection with {self.address}')
        self.client_socket.close()
        sys.exit()

    @staticmethod
    def get_file_property(filepath):
        def get_file_mode():
            modes = [
                stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR,
                stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP,
                stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH,
            ]
            mode = st.st_mode
            fullmode = ''
            fullmode += os.path.isdir(filepath) and 'd' or '-'

            for i in range(9):
                fullmode += bool(mode & modes[i]) and 'rwxrwxrwx'[i] or '-'
            return fullmode

        st = os.stat(filepath)
        file_msg = [
            get_file_mode(),
            str(st.st_nlink),
            pwd.getpwuid(st.st_uid).pw_name,
            grp.getgrgid(st.st_gid).gr_name,
            str(st.st_size),
            time.strftime('%b %d %H:%M', time.gmtime(st.st_mtime)),
            os.path.basename(filepath)
        ]
        return ' '.join(file_msg)


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
