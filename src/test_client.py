import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((socket.gethostname(), 21))
while True:
    msg = input().strip()
    if msg == 'q':
        break
    s.send(msg.encode('utf-8'))
    print(s.recv(1024).decode('utf-8'))
    # s.send(bytes("Hey there!!!", "utf-8"))

s.close()
