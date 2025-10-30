import socket
import pygame
import threading

# Configurações
WIDTH, HEIGHT = 600, 600
FPS = 30
PLAYER_SIZE = 60

GREY = (128, 128, 128)
RED = (255, 0, 0)
DARK_BLUE = (0, 46, 96)
LIGHT_BLUE = (173, 216, 230)

# Posição inicial dos jogadores
local_pos = [100, 100]
remote_pos = [300, 100]

# Criação do socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('191.4.249.214', 5000))  # Porta para receber
remote_addr = ('191.4.248.31', 5001)  # Endereço para enviar (inverso no outro lado)

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

# Inicia threads
threading.Thread(target=enviar_posicao, daemon=True).start()
threading.Thread(target=receber_posicao, daemon=True).start()

# Inicializa o Pygame
pygame.init()
tela = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("UDP Multiplayer Demo")
clock = pygame.time.Clock()

# Loop principal
running = True
while running:
    clock.tick(FPS)
    tela.fill(WHITE)

    # Eventos
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Movimento do jogador local
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        local_pos[0] -= 5
    if keys[pygame.K_RIGHT]:
        local_pos[0] += 5
    if keys[pygame.K_UP]:
        local_pos[1] -= 5
    if keys[pygame.K_DOWN]:
        local_pos[1] += 5

    # Desenha jogadores
    pygame.draw.rect(tela, RED, (*local_pos, PLAYER_SIZE, PLAYER_SIZE))
    pygame.draw.rect(tela, BLUE, (*remote_pos, PLAYER_SIZE, PLAYER_SIZE))

    pygame.display.flip()

pygame.quit()
