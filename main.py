import socket
import pygame
import threading
import math

# Configurações
SCREEN_WIDTH, SCREEN_HEIGHT = 600, 800
BOARD_WIDTH, BOARD_HEIGHT = 600, 600
FPS = 30
PLAYER_SIZE = BOARD_WIDTH // 10



GREY = (128, 128, 128)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
DARK_BLUE = (0, 46, 96)
LIGHT_BLUE = (173, 216, 230)

# Posição inicial dos jogadores
local_pos = [1,1]
remote_pos = [1,1]

local_user = []
user_ships = []


# Criação do socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('172.23.48.1', 5000))  # Porta para receber
remote_addr = ('172.23.48.1', 5001)  # Endereço para enviar (inverso no outro lado)

# Envia posição continuamente
def enviar_posicao():
    while True:
        msg = f"{local_pos[0]},{local_pos[1]}"
        sock.sendto(msg.encode(), remote_addr)

# Recebe posição do outro jogador
def receber_posicao():
    global remote_pos
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            x, y = map(int, data.decode().split(","))
            remote_pos = [x, y]
        except:
            continue

def draw_grid(surface, color, tile_size, board_width, board_height):
    # Draw vertical lines
    for x in range(0, board_width, tile_size):
        pygame.draw.line(surface, color, (x, 0), (x, board_height))

    # Draw horizontal lines
    for y in range(0, board_height+1, tile_size):
        pygame.draw.line(surface, color, (0, y), (board_width, y))

def set_ship(x,y, user_ships):
    x, y = calculate_position(x,y)
    if user_ships == local_user:
        paint_block(x, y, GREY)
    user_ships.append((x,y))

def paint_block(x, y, color):
    rect = pygame.Rect((x)*PLAYER_SIZE, (y)*PLAYER_SIZE, PLAYER_SIZE, PLAYER_SIZE)
    #pygame.draw.rect(tela, color, (x-1, y-1, PLAYER_SIZE-2, PLAYER_SIZE-2))
    pygame.draw.rect(tela, color, rect)

def calculate_position(x, y):
    x = math.floor(x/PLAYER_SIZE)
    y = math.floor(y/PLAYER_SIZE)
    return x, y

# Inicia threads
threading.Thread(target=enviar_posicao, daemon=True).start()
threading.Thread(target=receber_posicao, daemon=True).start()

# Inicializa o Pygame
pygame.init()
tela = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("UDP Multiplayer Demo")
clock = pygame.time.Clock()

# Loop principal
tela.fill(LIGHT_BLUE)
draw_grid(tela, BLACK,PLAYER_SIZE, BOARD_WIDTH, BOARD_HEIGHT)
running = True
while running:
    events = pygame.event.get()
    clock.tick(FPS)


    # Eventos
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            set_ship(pygame.mouse.get_pos()[0], pygame.mouse.get_pos()[1], local_user)
            print(pygame.mouse.get_pos())

    pygame.display.update()

pygame.quit()
