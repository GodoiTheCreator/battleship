import socket
import pygame
import threading
import math
import time
import sys


# Ler portas via argumento
if len(sys.argv) != 3:
    print("Uso correto: python batalha_naval.py <porta_escuta> <porta_envio>")
    print("Exemplo jogador 1: python batalha_naval.py 5000 5001")
    print("Exemplo jogador 2: python batalha_naval.py 5001 5000")
    sys.exit(1)

PORT_LISTEN = int(sys.argv[1])   # Porta que este jogador escuta
PORT_SEND = int(sys.argv[2])     # Porta que envia para o outro

print(f"[INFO] Escutando na porta {PORT_LISTEN}, enviando para porta {PORT_SEND}")


# Configurações do jogo
SCREEN_WIDTH, SCREEN_HEIGHT = 600, 800
BOARD_WIDTH, BOARD_HEIGHT = 600, 600
FPS = 30
PLAYER_SIZE = BOARD_WIDTH // 10


GREY = (128, 128, 128)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
LIGHT_BLUE = (173, 216, 230)

# Posições
local_pos = [1, 1]
remote_pos = [1, 1]
local_user = []


# Criar socket UDP (cada um bind na SUA porta)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", PORT_LISTEN))  # Cada instância usa porta diferente

remote_addr = ("127.0.0.1", PORT_SEND)  # Envia localmente entre instâncias


# Enviar posição continuamente
def enviar_posicao():
    while True:
        try:
            msg = f"{local_pos[0]},{local_pos[1]}"
            sock.sendto(msg.encode(), remote_addr)
        except Exception as e:
            print("[ERRO envio]:", e)
        time.sleep(0.1)


# Receber posição remota
def receber_posicao():
    global remote_pos
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            x, y = map(int, data.decode().split(","))
            if 0 <= x <= 9 and 0 <= y <= 9:
                remote_pos = [x, y]
        except:
            continue

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


# Inicia Threads
threading.Thread(target=enviar_posicao, daemon=True).start()
threading.Thread(target=receber_posicao, daemon=True).start()

# Pygame
pygame.init()
tela = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("UDP Multiplayer (Portas por parâmetro)")
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
