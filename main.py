import socket
import pygame
import threading
import math
import time
import sys

# PARÂMETROS DE LINHA DE COMANDO
if len(sys.argv) != 3:
    print("Uso correto:")
    print("python main.py <porta_escuta_udp> <porta_envio_udp>")
    print("\nExemplo jogador 1:")
    print("python main.py 5000 5001")
    print("\nExemplo jogador 2:")
    print("python main.py 5001 5000")
    sys.exit(1)

PORT_UDP_LISTEN = int(sys.argv[1])
PORT_UDP_SEND = int(sys.argv[2])

PORT_TCP_LISTEN = 5001  # Porta TCP fixa

print(f"[INFO] UDP escutando em {PORT_UDP_LISTEN}, enviando para {PORT_UDP_SEND}")
print(f"[INFO] TCP escutando em {PORT_TCP_LISTEN}")

# CONFIGURAÇÕES DO JOGO
SCREEN_WIDTH, SCREEN_HEIGHT = 600, 800
BOARD_WIDTH, BOARD_HEIGHT = 600, 600
FPS = 30
PLAYER_SIZE = BOARD_WIDTH // 10

GREY = (128, 128, 128)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
LIGHT_BLUE = (173, 216, 230)

local_pos = [1, 1]
remote_pos = [1, 1]
local_user = []

# UDP
sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_udp.bind(("", PORT_UDP_LISTEN))
sock_udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

remote_addr = ("127.0.0.1", PORT_UDP_SEND)

# TCP
sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock_tcp.bind(("", PORT_TCP_LISTEN))
sock_tcp.listen(5)

def send_tcp(ip, port, msg):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.send(msg.encode())
        s.close()
    except Exception as e:
        print("[ERRO TCP envio]:", e)

# THREAD: Enviar posição via UDP
def enviar_posicao():
    while True:
        try:
            msg = f"{local_pos[0]},{local_pos[1]}"
            sock_udp.sendto(msg.encode(), remote_addr)
        except Exception as e:
            print("[ERRO envio UDP]:", e)
        time.sleep(0.1)

# THREAD: Receber posição via UDP
def receber_posicao():
    global remote_pos
    while True:
        try:
            data, _ = sock_udp.recvfrom(1024)
            x, y = map(int, data.decode().split(","))
            if 0 <= x <= 9 and 0 <= y <= 9:
                remote_pos = [x, y]
        except:
            continue

# THREAD: Listener TCP
def tcp_listener():
    print("[TCP] Aguardando conexões...")

    while True:
        try:
            conn, addr = sock_tcp.accept()
            ip_remoto = addr[0]

            data = conn.recv(1024).decode().strip()
            print(f"[TCP] Recebido de {ip_remoto}: {data}")

        
            if data.startswith("scout:"):
                print("[TCP] Scout recebido")

            elif data == "hit":
                print("[TCP] Fui acertado!")

            elif data.startswith("info:"):
                print("[TCP] Informação de direção recebida.")

            conn.close()
        except Exception as e:
            print("[ERRO TCP listener]:", e)

# FUNÇÕES DO JOGO
def draw_grid(surface):
    for x in range(0, BOARD_WIDTH + 1, PLAYER_SIZE):
        pygame.draw.line(surface, BLACK, (x, 0), (x, BOARD_HEIGHT))

    for y in range(0, BOARD_HEIGHT + 1, PLAYER_SIZE):
        pygame.draw.line(surface, BLACK, (0, y), (BOARD_WIDTH, y))

def calculate_position(x, y):
    return x // PLAYER_SIZE, y // PLAYER_SIZE

def paint_block(surface, x, y, color):
    rect = pygame.Rect(x * PLAYER_SIZE, y * PLAYER_SIZE, PLAYER_SIZE, PLAYER_SIZE)
    pygame.draw.rect(surface, color, rect)

def set_ship(x, y, user_ships):
    cx, cy = calculate_position(x, y)
    cx = max(0, min(9, cx))
    cy = max(0, min(9, cy))
    local_pos[0], local_pos[1] = cx, cy
    if (cx, cy) not in user_ships:
        user_ships.append((cx, cy))

# THREADS
threading.Thread(target=enviar_posicao, daemon=True).start()
threading.Thread(target=receber_posicao, daemon=True).start()
threading.Thread(target=tcp_listener, daemon=True).start()

# LOOP PYGAME
pygame.init()
tela = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("UDP + TCP Multiplayer")
clock = pygame.time.Clock()

running = True
while running:
    clock.tick(FPS)
    tela.fill(LIGHT_BLUE)
    draw_grid(tela)

    # desenhar local e remoto
    paint_block(tela, local_pos[0], local_pos[1], GREY)
    paint_block(tela, remote_pos[0], remote_pos[1], RED)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            set_ship(mx, my, local_user)

    pygame.display.update()

pygame.quit()

#TESTE TCP MANUAL
#TERMINAL A: python main.py 5000 5001
#TERMINAL B:
# import socket
#s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#s.connect(("127.0.0.1", 5001))
#s.send(b"hit")
#s.close()