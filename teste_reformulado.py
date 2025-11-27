"""
batalha_p2p_reformulado.py
Versão refatorada e simplificada do backend para fins didáticos.
Mantém a mesma UI e funcionalidades.
"""

import socket
import threading
import pygame
import random
import time
import ast
import sys
import traceback
import queue

# --- CONFIGURAÇÕES ---
GRID_SIZE = 10
CELL = 48
SIDEBAR = 320
WIDTH = GRID_SIZE * CELL + SIDEBAR
HEIGHT = GRID_SIZE * CELL + 260  # Altura corrigida
FPS = 30

UDP_PORT = 5000
TCP_PORT = 5001
COOLDOWN = 5.0

class BattleshipGame:
    def __init__(self):
        self.running = True
        self.lock = threading.RLock()
        
        # Estado do Jogo
        self.ship_x = random.randint(0, GRID_SIZE - 1)
        self.ship_y = random.randint(0, GRID_SIZE - 1)
        self.participants = []
        self.hits_received = 0
        self.hits_by_us = {}  # {ip: count}
        self.message_log = []
        
        # Controle de Envio
        self.last_sent_time = 0.0
        self.action_queue = queue.Queue()
        
        # Rede
        self.own_ip = self.get_local_ip()
        self.udp_sock = self.make_udp_socket()
        self.tcp_sock = self.make_tcp_socket()
        
        # UI State
        self.selected_cell = None
        self.input_ip = ""
        self.input_active = False
        self.buttons = {}
        self.init_buttons()

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def make_udp_socket(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except:
            pass
        s.bind(('', UDP_PORT))
        return s

    def make_tcp_socket(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            pass
        s.bind(('', TCP_PORT))
        s.listen(5)
        return s

    def log(self, text):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {text}"
        with self.lock:
            self.message_log.append(entry)
            if len(self.message_log) > 200:
                self.message_log.pop(0)
        print(entry)

    # --- GERENCIAMENTO DE ESTADO ---

    def add_participant(self, ip):
        if ip == self.own_ip: return
        with self.lock:
            if ip not in self.participants:
                self.participants.append(ip)
                self.log(f"Novo participante: {ip}")

    def remove_participant(self, ip):
        with self.lock:
            if ip in self.participants:
                self.participants.remove(ip)
                self.log(f"Saiu: {ip}")

    def register_hit_received(self, x, y, shooter_ip):
        with self.lock:
            self.hits_received += 1
        self.log(f"Fui atingido por {shooter_ip} em ({x},{y})")

    def register_hit_dealt(self, target_ip):
        with self.lock:
            self.hits_by_us.setdefault(target_ip, 0)
            self.hits_by_us[target_ip] += 1
        self.log(f"Acertei {target_ip}!")

    # --- MÉTODOS DE REDE (RECEBIMENTO) ---

    def udp_listener(self):
        self.log(f"UDP ouvindo na porta {UDP_PORT}")
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(4096)
                msg = data.decode(errors="ignore").strip()
                ip = addr[0]
                # Processa em thread separada para não bloquear o listener
                threading.Thread(target=self.process_udp_message, args=(msg, ip), daemon=True).start()
            except Exception as e:
                if self.running: self.log(f"Erro UDP Listener: {e}")

    def tcp_listener(self):
        self.log(f"TCP ouvindo na porta {TCP_PORT}")
        while self.running:
            try:
                conn, addr = self.tcp_sock.accept()
                ip = addr[0]
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
                    msg = data.decode(errors="ignore").strip()
                    threading.Thread(target=self.process_tcp_message, args=(msg, ip), daemon=True).start()
            except Exception as e:
                if self.running: self.log(f"Erro TCP Listener: {e}")

    def process_udp_message(self, msg, ip):
        self.log(f"UDP <- {ip}: {msg}")
        
        if msg == "Conectando":
            self.add_participant(ip)
            # Envia lista de participantes via TCP para quem entrou
            with self.lock:
                current_list = [p for p in self.participants if p != self.own_ip]
            if ip not in current_list: current_list.append(ip)
            
            self.send_tcp(ip, f"participantes: {current_list}")

        elif msg.startswith("shot:"):
            try:
                _, coords = msg.split(":", 1)
                x, y = map(int, coords.split(","))
                
                # Verifica se acertou
                hit = False
                with self.lock:
                    if x == self.ship_x and y == self.ship_y:
                        hit = True
                
                if hit:
                    self.register_hit_received(x, y, ip)
                    self.send_tcp(ip, "hit")
                else:
                    self.log(f"Tiro de {ip} em ({x},{y}) errou.")
            except:
                self.log("Erro ao processar tiro UDP")

        elif msg == "moved":
            self.log(f"{ip} se moveu.")

        elif msg == "saindo":
            self.remove_participant(ip)

    def process_tcp_message(self, msg, ip):
        self.log(f"TCP <- {ip}: {msg}")

        if msg.startswith("participantes:"):
            try:
                lista_str = msg.split(":", 1)[1].strip()
                novos = ast.literal_eval(lista_str)
                for p in novos:
                    if isinstance(p, str) and p != self.own_ip:
                        self.add_participant(p)
                self.add_participant(ip)
            except:
                self.log("Erro ao processar lista de participantes")

        elif msg.startswith("scout:"):
            try:
                _, coords = msg.split(":", 1)
                x, y = map(int, coords.split(","))
                
                hit = False
                with self.lock:
                    if x == self.ship_x and y == self.ship_y:
                        hit = True
                    sx, sy = self.ship_x, self.ship_y
                
                if hit:
                    self.register_hit_received(x, y, ip)
                    self.send_tcp(ip, "hit")
                else:
                    # Dica de direção
                    dx = 1 if sx > x else -1
                    dy = 1 if sy > y else -1
                    self.send_tcp(ip, f"info:{dx},{dy}")
            except:
                self.log("Erro ao processar scout")

        elif msg == "hit":
            self.register_hit_dealt(ip)

        elif msg.startswith("info:"):
            self.log(f"Dica de {ip}: {msg.split(':')[1]}")

    # --- MÉTODOS DE REDE (ENVIO) ---

    def send_udp_packet(self, ip, text):
        try:
            # Usa socket temporário para envio direcionado ou broadcast
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if ip == '<broadcast>':
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(text.encode(), (ip, UDP_PORT))
            s.close()
            self.log(f"UDP -> {ip}: {text}")
        except Exception as e:
            self.log(f"Erro envio UDP: {e}")

    def send_tcp(self, ip, text):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, TCP_PORT))
            s.sendall(text.encode())
            # TCP pode ter resposta imediata (ex: handshake), mas aqui tratamos assíncrono na maioria
            # Se houver resposta imediata, seria lida aqui. O código original tentava ler.
            # Vamos manter simples: envia e fecha. A resposta vem em nova conexão se necessário.
            s.close()
            self.log(f"TCP -> {ip}: {text}")
        except Exception as e:
            self.log(f"Erro envio TCP para {ip}: {e}")

    def sender_worker(self):
        self.log("Sender worker iniciado")
        while self.running:
            try:
                # Pega ação da fila (bloqueia até ter algo)
                action = self.action_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Verifica Cooldown
            with self.lock:
                now = time.time()
                wait = COOLDOWN - (now - self.last_sent_time)
            
            if wait > 0:
                time.sleep(wait)

            # Executa Ação
            kind = action[0]
            try:
                if kind == "broadcast_connect":
                    self.send_udp_packet('<broadcast>', "Conectando")

                elif kind == "shot":
                    _, x, y = action
                    with self.lock:
                        targets = list(self.participants)
                    for p in targets:
                        self.send_udp_packet(p, f"shot:{x},{y}")

                elif kind == "scout":
                    _, x, y, target_ip = action
                    self.send_tcp(target_ip, f"scout:{x},{y}")

                elif kind == "move":
                    _, dx, dy = action
                    with self.lock:
                        self.ship_x = max(0, min(GRID_SIZE - 1, self.ship_x + dx))
                        self.ship_y = max(0, min(GRID_SIZE - 1, self.ship_y + dy))
                        targets = list(self.participants)
                    for p in targets:
                        self.send_udp_packet(p, "moved")
                
                elif kind == "leave":
                    with self.lock:
                        targets = list(self.participants)
                    for p in targets:
                        self.send_udp_packet(p, "saindo")

            except Exception as e:
                self.log(f"Erro ao executar ação {kind}: {e}")

            with self.lock:
                self.last_sent_time = time.time()
            
            self.action_queue.task_done()

    # --- UI E GAME LOOP ---

    def init_buttons(self):
        x0 = GRID_SIZE * CELL + 12
        base = HEIGHT - 180
        self.buttons = {
            "shot": (pygame.Rect(x0, base, 120, 34), "SHOT"),
            "scout": (pygame.Rect(x0 + 130, base, 120, 34), "SCOUT"),
            "move+X": (pygame.Rect(x0, base + 44, 56, 34), "+ X"),
            "move-X": (pygame.Rect(x0 + 64, base + 44, 56, 34), "- X"),
            "move+Y": (pygame.Rect(x0 + 130, base + 44, 56, 34), "+ Y"),
            "move-Y": (pygame.Rect(x0 + 196, base + 44, 56, 34), "- Y"),
            "ping": (pygame.Rect(x0, base + 92, 120, 34), "PING"),
            "leave": (pygame.Rect(x0 + 130, base + 92, 120, 34), "SAIR"),
        }

    def draw_ui(self, screen, font, bigfont):
        # Grid
        for gx in range(GRID_SIZE):
            for gy in range(GRID_SIZE):
                rect = pygame.Rect(gx * CELL, gy * CELL, CELL, CELL)
                pygame.draw.rect(screen, (50, 50, 90), rect)
                pygame.draw.rect(screen, (80, 80, 110), rect, 1)

        # Meu Navio
        with self.lock:
            sx, sy = self.ship_x, self.ship_y
        srect = pygame.Rect(sx * CELL + 4, sy * CELL + 4, CELL - 8, CELL - 8)
        pygame.draw.rect(screen, (20, 140, 220), srect)

        # Seleção
        if self.selected_cell:
            rx, ry = self.selected_cell
            rect = pygame.Rect(rx * CELL + 2, ry * CELL + 2, CELL - 4, CELL - 4)
            pygame.draw.rect(screen, (255, 255, 0), rect, 3)

        # Sidebar
        sidebar_rect = pygame.Rect(GRID_SIZE * CELL, 0, SIDEBAR, HEIGHT)
        pygame.draw.rect(screen, (18, 18, 25), sidebar_rect)

        x0 = GRID_SIZE * CELL + 12
        y = 8

        screen.blit(bigfont.render("Batalha Naval P2P", True, (220, 220, 220)), (x0, y)); y += 28
        screen.blit(font.render(f"Meu IP: {self.own_ip}", True, (200, 200, 200)), (x0, y)); y += 20
        screen.blit(font.render(f"Minha posição: ({sx},{sy})", True, (200, 200, 200)), (x0, y)); y += 24

        with self.lock:
            passed = time.time() - self.last_sent_time
            cd = max(0.0, COOLDOWN - passed)
            plist = list(self.participants[-10:])
            hits_recv = self.hits_received
            hits_dealt = dict(self.hits_by_us)
            logs = list(self.message_log[-12:])

        screen.blit(font.render(f"Cooldown: {cd:.1f}s", True, (255, 200, 50)), (x0, y)); y += 26
        screen.blit(bigfont.render("Participantes", True, (200, 200, 220)), (x0, y)); y += 24

        for p in plist:
            screen.blit(font.render(p, True, (170, 170, 170)), (x0, y)); y += 18
        y += 8

        screen.blit(font.render(f"Fui atingido: {hits_recv}", True, (255, 120, 120)), (x0, y)); y += 20
        screen.blit(font.render("Hits que causei:", True, (150, 220, 150)), (x0, y)); y += 20
        for ip, h in hits_dealt.items():
            screen.blit(font.render(f"{ip}: {h}", True, (150, 220, 150)), (x0, y)); y += 18

        # Botões
        mouse = pygame.mouse.get_pos()
        for key, (rect, label) in self.buttons.items():
            hovered = rect.collidepoint(mouse)
            color = (40, 120, 40) if not hovered else (60, 150, 60)
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, (180, 180, 180), rect, 2)
            text = font.render(label, True, (255, 255, 255))
            screen.blit(text, (rect.x + (rect.width - text.get_width()) // 2,
                               rect.y + (rect.height - text.get_height()) // 2))

        # Log Box
        ly = HEIGHT - (18 * 13) - 6
        box = pygame.Rect(4, ly - 6, GRID_SIZE * CELL - 8, 18 * 13 + 12)
        pygame.draw.rect(screen, (8, 8, 20), box)
        pygame.draw.rect(screen, (40, 40, 60), box, 1)
        for i, line in enumerate(logs):
            screen.blit(font.render(line, True, (200, 200, 200)), (6, ly + i * 18))

        # Input Box
        ibox = pygame.Rect(x0, HEIGHT - 40, 250, 28)
        pygame.draw.rect(screen, (22, 22, 30), ibox)
        pygame.draw.rect(screen, (120, 120, 120), ibox, 2)
        txt = font.render("IP (scout): " + self.input_ip, True, (210, 210, 210))
        screen.blit(txt, (ibox.x + 6, ibox.y + 5))

    def handle_input(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                pos = event.pos
                x, y = pos
                
                # Clique no Grid
                if x < GRID_SIZE * CELL and y < GRID_SIZE * CELL:
                    self.selected_cell = (x // CELL, y // CELL)
                    self.log(f"Selecionado: {self.selected_cell}")
                    return

                # Clique nos Botões
                for k, (rect, _) in self.buttons.items():
                    if rect.collidepoint(pos):
                        self.process_button_click(k)
                        return

                # Clique no Input
                x0 = GRID_SIZE * CELL + 12
                ibox = pygame.Rect(x0, HEIGHT - 40, 250, 28)
                self.input_active = ibox.collidepoint(pos)

        elif event.type == pygame.KEYDOWN:
            if self.input_active:
                if event.key == pygame.K_BACKSPACE:
                    self.input_ip = self.input_ip[:-1]
                else:
                    if event.unicode in "0123456789.":
                        self.input_ip += event.unicode
            
            if event.key == pygame.K_p:
                self.action_queue.put(("broadcast_connect",))
            if event.key == pygame.K_ESCAPE:
                self.action_queue.put(("leave",))
                self.running = False

    def process_button_click(self, key):
        if key == "shot":
            if self.selected_cell:
                self.action_queue.put(("shot", self.selected_cell[0], self.selected_cell[1]))
            else:
                self.log("Selecione uma célula!")
        
        elif key == "scout":
            if self.selected_cell and self.input_ip:
                self.action_queue.put(("scout", self.selected_cell[0], self.selected_cell[1], self.input_ip))
            else:
                self.log("Precisa de IP e Célula!")
        
        elif key.startswith("move"):
            axis = "X" if "X" in key else "Y"
            sign = 1 if "+" in key else -1
            self.action_queue.put(("move", sign if axis == "X" else 0, sign if axis == "Y" else 0))
        
        elif key == "ping":
            self.action_queue.put(("broadcast_connect",))
        
        elif key == "leave":
            self.action_queue.put(("leave",))
            self.running = False

    def run(self):
        pygame.init()
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Batalha Naval P2P (Refatorado)")
        font = pygame.font.SysFont("consolas", 16)
        bigfont = pygame.font.SysFont("consolas", 20)
        clock = pygame.time.Clock()

        # Inicia Threads
        threading.Thread(target=self.udp_listener, daemon=True).start()
        threading.Thread(target=self.tcp_listener, daemon=True).start()
        threading.Thread(target=self.sender_worker, daemon=True).start()

        time.sleep(0.5)
        self.action_queue.put(("broadcast_connect",))

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.action_queue.put(("leave",))
                    self.running = False
                else:
                    self.handle_input(event)

            screen.fill((10, 10, 30))
            self.draw_ui(screen, font, bigfont)
            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()
        self.show_final_score()

    def show_final_score(self):
        print("\n=== FIM DE JOGO ===")
        print(f"Hits Recebidos: {self.hits_received}")
        print(f"Hits Causados: {sum(self.hits_by_us.values())}")
        sys.exit(0)

if __name__ == "__main__":
    game = BattleshipGame()
    game.run()
