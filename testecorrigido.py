"""
batalha_p2p_pygame.py
Jogo P2P Batalha Naval - Pygame + UDP(5000)/TCP(5001)
"""

import socket
import threading
import pygame
import random
import time
import ast
import sys
import traceback

# --- Configurações Globais ---
GRID_SIZE = 10
CELL = 48
SIDEBAR = 320
WIDTH = GRID_SIZE * CELL + SIDEBAR
HEIGHT = GRID_SIZE * CELL + 260
FPS = 30

UDP_PORT = 5000
TCP_PORT = 5001

# Cooldowns diferenciados
COOLDOWN_MOVE = 20.0
COOLDOWN_ACTION = 10.0

# Estado do Jogo
ship_x = random.randint(0, GRID_SIZE - 1)
ship_y = random.randint(0, GRID_SIZE - 1)
RUNNING = True

# Estruturas de Dados (com Locks para Thread Safety)
participants = []
participants_lock = threading.Lock()

pending_action = None
pending_lock = threading.Lock()

last_sent_time = 0.0
last_cooldown_duration = 0.0
last_sent_lock = threading.Lock()

hits_received = 0
hits_by_us = {}
hits_lock = threading.Lock()

message_log = []
log_lock = threading.Lock()
MAX_LOG = 200

# --- Sistema de Log ---
def log(s):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {s}"
    with log_lock:
        message_log.append(entry)
        if len(message_log) > MAX_LOG:
            message_log.pop(0)
    print(entry)

# --- Utilitários de Rede ---
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

OWN_IP = get_local_ip()

def safe_add_participant(ip):
    if ip == OWN_IP: return False
    with participants_lock:
        if ip in participants: return False
        participants.append(ip)
    log(f"Participante adicionado: {ip}")
    return True

def safe_remove_participant(ip):
    with participants_lock:
        if ip in participants:
            participants.remove(ip)
            log(f"Participante removido: {ip}")

# --- Criação de Sockets ---
def make_udp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except Exception: pass
    s.bind(('', UDP_PORT))
    return s

def make_tcp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception: pass
    s.bind(('', TCP_PORT))
    s.listen(5)
    return s

# --- Lógica de Mensagens (Handlers) ---
def handle_udp_message(msg, addr_ip):
    global hits_received
    msg = msg.strip()
    log(f"UDP <- {addr_ip}: '{msg}'")

    if msg == "Conectando":
        safe_add_participant(addr_ip)
        with participants_lock:
            plist = [p for p in participants if p != OWN_IP]
        if addr_ip not in plist: plist.append(addr_ip)
        
        # Envia lista atualizada via TCP
        payload = f"participantes: {plist}"
        threading.Thread(target=send_tcp, args=(addr_ip, payload), daemon=True).start()

    elif msg.startswith("shot:"):
        try:
            _, coords = msg.split(":", 1)
            x, y = map(int, coords.split(","))
        except: return

        if x == ship_x and y == ship_y:
            threading.Thread(target=send_tcp, args=(addr_ip, "hit"), daemon=True).start()
            with hits_lock: hits_received += 1
            log(f"Fui atingido por {addr_ip} em ({x},{y})")
        else:
            log(f"Tiro de {addr_ip} errou ({x},{y})")

    elif msg == "moved":
        log(f"{addr_ip} se moveu.")

    elif msg == "saindo":
        safe_remove_participant(addr_ip)

def handle_tcp_message(msg, addr_ip):
    global hits_received
    msg = msg.strip()
    log(f"TCP <- {addr_ip}: '{msg}'")

    if msg.startswith("participantes:"):
        try:
            rhs = msg.split(":", 1)[1].strip()
            plist = ast.literal_eval(rhs)
            for ip in plist:
                if isinstance(ip, str) and ip != OWN_IP:
                    safe_add_participant(ip)
            safe_add_participant(addr_ip)
        except Exception: pass

    elif msg.startswith("scout:"):
        try:
            _, coords = msg.split(":", 1)
            x, y = map(int, coords.split(","))
        except: return

        if x == ship_x and y == ship_y:
            threading.Thread(target=send_tcp, args=(addr_ip, "hit"), daemon=True).start()
            with hits_lock: hits_received += 1
        else:
            # Retorna dica de direção
            x_rel = 1 if ship_x > x else -1
            y_rel = 1 if ship_y > y else -1
            payload = f"info:{x_rel},{y_rel}"
            threading.Thread(target=send_tcp, args=(addr_ip, payload), daemon=True).start()

    elif msg == "hit":
        with hits_lock:
            hits_by_us[addr_ip] = hits_by_us.get(addr_ip, 0) + 1

    elif msg.startswith("info:"):
        try:
            _, coords = msg.split(":", 1)
            xr, yr = map(int, coords.split(","))
            log(f"Dica de {addr_ip}: x_rel={xr}, y_rel={yr}")
        except: pass

# --- Funções de Envio ---
def send_udp(ip, text):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(text.encode(), (ip, UDP_PORT))
        s.close()
        log(f"UDP -> {ip}: '{text}'")
    except Exception as e: log(f"Erro UDP: {e}")

def broadcast_conectar():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(b"Conectando", ('<broadcast>', UDP_PORT))
        s.close()
        log("Broadcast enviado.")
    except Exception: pass

def send_tcp(ip, text):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((ip, TCP_PORT))
        s.sendall(text.encode())
        try:
            data = s.recv(4096)
            if data: handle_tcp_message(data.decode(), ip)
        except: pass
        s.close()
        log(f"TCP -> {ip}: '{text}'")
    except Exception as e: log(f"Erro TCP -> {ip}: {e}")

# --- Threads de Rede ---
def udp_listener_thread():
    try: s = make_udp_socket()
    except: return
    log(f"UDP ouvindo na porta {UDP_PORT}")
    while RUNNING:
        try:
            data, addr = s.recvfrom(4096)
            threading.Thread(target=handle_udp_message, args=(data.decode(errors="ignore"), addr[0]), daemon=True).start()
        except: pass

def tcp_listener_thread():
    try: s = make_tcp_socket()
    except: return
    log(f"TCP ouvindo na porta {TCP_PORT}")
    while RUNNING:
        try:
            conn, addr = s.accept()
            data = b""
            try:
                conn.settimeout(2.0)
                while True:
                    part = conn.recv(4096)
                    if not part: break
                    data += part
            except: pass
            conn.close()
            if data:
                threading.Thread(target=handle_tcp_message, args=(data.decode(errors="ignore"), addr[0]), daemon=True).start()
        except: pass

def sender_thread():
    global pending_action, ship_x, ship_y, last_sent_time, last_cooldown_duration
    log("Sender thread iniciada.")

    while RUNNING:
        time.sleep(0.1)
        with pending_lock:
            action = pending_action
            pending_action = None

        if not action: continue

        # Verifica Cooldown
        with last_sent_lock:
            now = time.time()
            wait = last_cooldown_duration - (now - last_sent_time)
        if wait > 0: time.sleep(wait)

        # Executa Ação
        try:
            cmd = action[0]
            if cmd == "shot":
                _, x, y = action
                with participants_lock: targets = participants.copy()
                for ip in targets: send_udp(ip, f"shot:{x},{y}")

            elif cmd == "scout":
                _, x, y, ip = action
                send_tcp(ip, f"scout:{x},{y}")

            elif cmd == "move":
                _, sign, axis = action
                delta = 1 if sign == "+" else -1
                if axis == "X":
                    ship_x = max(0, min(GRID_SIZE - 1, ship_x + delta))
                else:
                    ship_y = max(0, min(GRID_SIZE - 1, ship_y + delta))
                
                with participants_lock: targets = participants.copy()
                for ip in targets: send_udp(ip, "moved")

        except Exception as e: log(f"Erro envio: {e}")

        # Atualiza Cooldown
        with last_sent_lock:
            last_sent_time = time.time()
            if action[0] == "move":
                last_cooldown_duration = COOLDOWN_MOVE
            else:
                last_cooldown_duration = COOLDOWN_ACTION

# --- Interface Gráfica (Pygame) ---
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Batalha Naval P2P")
font = pygame.font.SysFont("consolas", 16)
bigfont = pygame.font.SysFont("consolas", 20)

selected_cell = None
input_ip = ""
input_active = False
buttons = {}

def init_buttons():
    global buttons
    x0 = GRID_SIZE * CELL + 12
    base = HEIGHT - 180
    buttons = {
        "shot": (pygame.Rect(x0, base, 120, 34), "SHOT"),
        "scout": (pygame.Rect(x0 + 130, base, 120, 34), "SCOUT"),
        "move+X": (pygame.Rect(x0, base + 44, 56, 34), "+ X"),
        "move-X": (pygame.Rect(x0 + 64, base + 44, 56, 34), "- X"),
        "move+Y": (pygame.Rect(x0 + 130, base + 44, 56, 34), "+ Y"),
        "move-Y": (pygame.Rect(x0 + 196, base + 44, 56, 34), "- Y"),
        "ping": (pygame.Rect(x0, base + 92, 120, 34), "PING"),
        "leave": (pygame.Rect(x0 + 130, base + 92, 120, 34), "SAIR"),
    }
init_buttons()

def draw_ui():
    screen.fill((10, 10, 30))

    # Grid
    for gx in range(GRID_SIZE):
        for gy in range(GRID_SIZE):
            rect = pygame.Rect(gx * CELL, gy * CELL, CELL, CELL)
            pygame.draw.rect(screen, (50, 50, 90), rect)
            pygame.draw.rect(screen, (80, 80, 110), rect, 1)

    # Meu Navio
    srect = pygame.Rect(ship_x * CELL + 4, ship_y * CELL + 4, CELL - 8, CELL - 8)
    pygame.draw.rect(screen, (20, 140, 220), srect)

    # Sidebar
    pygame.draw.rect(screen, (18, 18, 25), pygame.Rect(GRID_SIZE * CELL, 0, SIDEBAR, HEIGHT))
    x0 = GRID_SIZE * CELL + 12
    y = 8

    # Info
    screen.blit(bigfont.render("Batalha Naval P2P", True, (220, 220, 220)), (x0, y)); y += 28
    screen.blit(font.render(f"Meu IP: {OWN_IP}", True, (200, 200, 200)), (x0, y)); y += 20
    screen.blit(font.render(f"Posição: ({ship_x},{ship_y})", True, (200, 200, 200)), (x0, y)); y += 24

    # Cooldown Display
    with last_sent_lock:
        passed = time.time() - last_sent_time
        lcd = last_cooldown_duration
    cd = max(0.0, lcd - passed)
    screen.blit(font.render(f"Cooldown: {cd:.1f}s", True, (255, 200, 50)), (x0, y)); y += 26

    # Participantes
    screen.blit(bigfont.render("Participantes", True, (200, 200, 220)), (x0, y)); y += 24
    with participants_lock:
        for p in participants[-10:]:
            screen.blit(font.render(p, True, (170, 170, 170)), (x0, y)); y += 18
    y += 8

    # Placar
    with hits_lock:
        screen.blit(font.render(f"Fui atingido: {hits_received}", True, (255, 120, 120)), (x0, y)); y += 20
        screen.blit(font.render("Meus Hits:", True, (150, 220, 150)), (x0, y)); y += 20
        for ip, h in hits_by_us.items():
            screen.blit(font.render(f"{ip}: {h}", True, (150, 220, 150)), (x0, y)); y += 18

    # Botões
    mouse = pygame.mouse.get_pos()
    for key, (rect, label) in buttons.items():
        color = (60, 150, 60) if rect.collidepoint(mouse) else (40, 120, 40)
        pygame.draw.rect(screen, color, rect)
        pygame.draw.rect(screen, (180, 180, 180), rect, 2)
        text = font.render(label, True, (255, 255, 255))
        screen.blit(text, (rect.x + (rect.width - text.get_width()) // 2, rect.y + (rect.height - text.get_height()) // 2))

    # Log
    with log_lock: lines = message_log[-12:]
    ly = HEIGHT - (18 * 13) - 6
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, (200, 200, 200)), (6, ly + i * 18))

    # Input Box
    ibox = pygame.Rect(x0, HEIGHT - 40, 250, 28)
    pygame.draw.rect(screen, (22, 22, 30), ibox)
    pygame.draw.rect(screen, (120, 120, 120), ibox, 2)
    screen.blit(font.render("IP (scout): " + input_ip, True, (210, 210, 210)), (ibox.x + 6, ibox.y + 5))

    # Seleção
    if selected_cell:
        rx, ry = selected_cell[0] * CELL, selected_cell[1] * CELL
        pygame.draw.rect(screen, (255, 255, 0), (rx + 2, ry + 2, CELL - 4, CELL - 4), 3)

    pygame.display.flip()

def handle_click(pos):
    global pending_action, selected_cell, input_ip, input_active
    x, y = pos

    # Clique no Grid
    if x < GRID_SIZE * CELL and y < GRID_SIZE * CELL:
        selected_cell = (x // CELL, y // CELL)
        log(f"Célula: {selected_cell}")
        return

    # Clique nos Botões
    for k, (rect, _) in buttons.items():
        if rect.collidepoint(pos):
            if k == "shot":
                if selected_cell:
                    with pending_lock: pending_action = ("shot", *selected_cell)
                else: log("Selecione uma célula.")
            
            elif k == "scout":
                if input_ip.strip() and selected_cell:
                    with pending_lock: pending_action = ("scout", *selected_cell, input_ip.strip())
                else: log("Digite IP e selecione célula.")

            elif k.startswith("move"):
                sign = "+" if "+" in k else "-"
                axis = "X" if "X" in k else "Y"
                with pending_lock: pending_action = ("move", sign, axis)

            elif k == "ping": broadcast_conectar()
            elif k == "leave":
                with participants_lock:
                    for ip in participants: send_udp(ip, "saindo")
                finish_and_exit()
            return

    # Clique no Input
    ibox = pygame.Rect(GRID_SIZE * CELL + 12, HEIGHT - 40, 250, 28)
    input_active = ibox.collidepoint(pos)

def finish_and_exit():
    global RUNNING
    RUNNING = False
    pygame.quit()
    
    with hits_lock:
        unique = len([ip for ip, h in hits_by_us.items() if h > 0])
        total = sum(hits_by_us.values())
        score = unique - hits_received

    print("\n=== SCORE FINAL ===")
    print(f"Fui atingido: {hits_received}")
    print(f"Jogadores atingidos: {unique}")
    print(f"Total hits causados: {total}")
    print(f"Score: {score}")
    sys.exit(0)

# --- Inicialização ---
threading.Thread(target=udp_listener_thread, daemon=True).start()
threading.Thread(target=tcp_listener_thread, daemon=True).start()
threading.Thread(target=sender_thread, daemon=True).start()

time.sleep(0.3)
broadcast_conectar()

clock = pygame.time.Clock()

while RUNNING:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            with participants_lock:
                for ip in participants: send_udp(ip, "saindo")
            finish_and_exit()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: handle_click(event.pos)

        elif event.type == pygame.KEYDOWN:
            if input_active:
                if event.key == pygame.K_BACKSPACE: input_ip = input_ip[:-1]
                else:
                    ch = event.unicode
                    if ch.isdigit() or ch in ".:" or ch.isalpha() or ch == "-": input_ip += ch
            
            if event.key == pygame.K_p: broadcast_conectar()
            if event.key == pygame.K_ESCAPE:
                with participants_lock:
                    for ip in participants: send_udp(ip, "saindo")
                finish_and_exit()

    draw_ui()
    clock.tick(FPS)
