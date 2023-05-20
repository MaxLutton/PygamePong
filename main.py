import sys
import pygame
import enum
import socket
import json
import select
import re

WINDOW_WIDTH = 640
WINDOW_HEIGHT = 480
BLACK = pygame.Color("black")
BLUE = pygame.Color("blue")
WHITE = pygame.Color("white")
GREEN = pygame.Color("green")


class GameEnums(enum.Enum):
    ALIVE = 1
    PAUSE = 2
    DEAD = 3


class GameStats:
    def __init__(self):
        self.score = 0
        self.lives = 3
        self.state = GameEnums.ALIVE

    def lose_life(self):
        print(f"Lost a life: {self.lives} -> {self.lives - 1}")
        self.lives -= 1
        if self.lives > 0:
            self.set_state(GameEnums.PAUSE)
        else:
            self.set_state(GameEnums.DEAD)
        return self.lives

    def score_point(self):
        self.score += 1

    def set_state(self, state):
        print(f"New game state: {state}")
        self.state = state

    def get_stat_text(self):
        text = f"Score: {self.score} ||| Lives: {self.lives}"
        return text


class Ball(pygame.sprite.Sprite):
    def __init__(self, x, y, game_stats: GameStats, speed=[0, 0]):
        super().__init__()
        self.image: pygame.surface.Surface = pygame.image.load(
            "intro_ball.gif").convert_alpha()
        self.init_x = x
        self.init_y = y
        self.init_speed = speed
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y
        self.speed = speed
        self.game_stats = game_stats

    def move(self):
        self.rect.move_ip(self.speed)
        # Right or left limits
        if self.rect.right > WINDOW_WIDTH or self.rect.left < 0:
            print("death!")
            self.game_stats.lose_life()
        # Top or bottom limits
        elif self.rect.bottom > WINDOW_HEIGHT or self.rect.top < 0:
            print("bump!")
            self.speed[1] = -self.speed[1]

    def reset_pos(self):
        self.rect.x = self.init_x
        self.rect.y = self.init_y
        self.speed = [0, 0]

    def restart(self):
        self.speed = self.init_speed


class Paddle(pygame.sprite.Sprite):
    def __init__(self, x, y, width, height, color):
        super().__init__()
        self.speed = [0, 0]
        self.width = width
        self.height = height
        self.init_x = x
        self.init_y = y
        self.image = pygame.Surface([width, height]).convert()
        self.image.fill(color)
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y

    def move(self):
        self.rect = self.rect.move(self.speed)
        # TODO: simplify using x,y?
        if self.rect.top < 0:
            print("wrap around!")
            self.rect.top = WINDOW_HEIGHT
            self.rect.bottom = WINDOW_HEIGHT + self.height
        elif self.rect.top > WINDOW_HEIGHT:
            print("wrap around!")
            self.rect.bottom = self.height
            self.rect.top = 0

    def reset_pos(self):
        self.rect.x = self.init_x
        self.rect.y = self.init_y
        self.speed = [0, 0]


class Server:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.pattern = re.compile(r"({[0-9a-zA-Z\":_ \[\],\-]+})")
        self.sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)  # TODO: udp faster
        print(f"binding server to {ip}:{port}")
        self.sock.bind((ip, port))
        self.sock.listen()
        print("waiting for connections...")
        self.conn_socket, addr = self.sock.accept()  # blocking
        print(f"got connection from {addr}")

    def send_state(self, paddle1, paddle2, ball, stats):
        _, write_list, _ = select.select([], [self.conn_socket], [], 0)
        if write_list:  # At most 1 socket
            send_dict = {
                "paddle1_xy": [paddle1.rect.x, paddle1.rect.y],
                "ball_xy": [ball.rect.x, ball.rect.y],
                "game_state": stats.state.name,
                "score": stats.score,
                "lives": stats.lives
            }
            write_list[0].sendall(bytes(json.dumps(send_dict), "utf-8"))

    def recv_state(self, paddle1, paddle2, ball, stats):
        read_list, _, _ = select.select([self.conn_socket], [], [], 0)
        if read_list:
            data = read_list[0].recv(4096)
            # TODO: if needed, remove regex for speed
            matches = re.findall(self.pattern, str(data, "utf-8"))
            if matches:
                try:
                    # use latest positions only
                    data_dict = json.loads(matches[-1])
                    paddle2.rect.x, paddle2.rect.y = data_dict["paddle2_xy"]
                except Exception as err:
                    print(f"Failed to parse: {err}")
                    print(data)
            else:
                print(f"recv runt data: {data}")


class Client:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.pattern = re.compile(r"({[0-9a-zA-Z\":_ \[\],\-]+})")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"trying to connect to: {ip}:{port}")
        self.sock.connect((ip, port))  # blocking
        print("connected!")

    def send_state(self, paddle1, paddle2, ball, stats):
        _, write_list, _ = select.select([], [self.sock], [], 0)
        if write_list:
            send_dict = {"paddle2_xy": [paddle2.rect.x, paddle2.rect.y]}
            write_list[0].sendall(bytes(json.dumps(send_dict), "utf-8"))

    def recv_state(self, paddle1, paddle2, ball, stats):
        read_list, _, _ = select.select([self.sock], [], [], 0)
        if read_list:
            data = read_list[0].recv(4096)
            matches = re.findall(self.pattern, str(data, "utf-8"))
            if matches:
                try:
                    data_dict = json.loads(matches[-1])
                    paddle1.rect.x, paddle1.rect.y = data_dict["paddle1_xy"]
                    ball.rect.x, ball.rect.y = data_dict["ball_xy"]
                    stats.state = GameEnums[data_dict["game_state"]]
                    stats.score = data_dict["score"]
                    stats.lives = data_dict["lives"]
                except Exception as err:
                    print(f"failed to parse: {err}")
                    print(data)
            else:
                print(f"recv runt data: {data}")


def main():
    # setup
    pygame.init()
    pygame.display.set_caption("Let's goooooo")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    stats = GameStats()
    stats_font = pygame.font.SysFont("", 24)
    game_over_font = pygame.font.SysFont("", 54)

    is_server = input("Server: Y/N") == "Y"
    ip = input("Enter ip for game:")

    # TODO: clean up class structures
    if is_server:
        peer = Server(ip, 65432)
    else:
        peer = Client(ip, 65432)

    # initialize sprites
    ball = Ball(WINDOW_WIDTH//2, WINDOW_HEIGHT//2, stats, speed=[-5, 0])
    paddle1 = Paddle(15, WINDOW_HEIGHT//2, 20, 90, BLUE)
    paddle2 = Paddle(WINDOW_WIDTH-30, WINDOW_HEIGHT//2, 30, 90, GREEN)

    # assign groups
    all_sprites = pygame.sprite.Group()
    all_sprites.add(ball)
    all_sprites.add(paddle1)
    all_sprites.add(paddle2)
    ballz = pygame.sprite.Group()
    ballz.add(ball)

    player_speed = [0, 0]
    while True:
        # handle input
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if is_server:
                    peer.conn_socket.close()
                    peer.sock.close()
                else:
                    peer.sock.close()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    player_speed = [0, -5]
                elif event.key == pygame.K_DOWN:
                    player_speed = [0, 5]
                elif event.key == pygame.K_SPACE and stats.state == GameEnums.PAUSE:
                    if is_server:
                        stats.set_state(GameEnums.ALIVE)
                        ball.restart()
                elif event.key == pygame.K_ESCAPE:
                    if is_server:
                        peer.conn_socket.close()
                        peer.sock.close()
                    else:
                        peer.sock.close()
                    sys.exit()
            elif event.type == pygame.KEYUP:
                if event.key in [pygame.K_UP, pygame.K_DOWN]:
                    player_speed = [0, 0]

        if is_server:
            paddle1.speed = player_speed
        else:
            paddle2.speed = player_speed

        # Receive updates over network
        peer.recv_state(paddle1, paddle2, ball, stats)

        # Server keeps track of points
        if is_server:
            # TODO: handle collisions from bottom of paddle
            if (pygame.sprite.spritecollideany(paddle1, ballz) or
                    pygame.sprite.spritecollideany(paddle2, ballz)):
                print("Ball hit!")
                ball.speed[0] = -ball.speed[0]
                stats.score_point()

        if stats.state == GameEnums.ALIVE:
            if is_server:
                ball.move()
                paddle1.move()
            else:
                paddle2.move()
        elif stats.state == GameEnums.PAUSE:
            ball.reset_pos()
            paddle1.reset_pos()
            paddle2.reset_pos()
        elif stats.state == GameEnums.DEAD:
            text = f"Game over! Final score: {stats.score} :D"
            font_size = game_over_font.size(text)
            text_pos = (WINDOW_WIDTH//2 -
                        font_size[0]//2, WINDOW_HEIGHT//2-font_size[1]//2)
            font_img = game_over_font.render(text, True, WHITE)
            screen.fill(BLACK)
            screen.blit(font_img, text_pos)
            pygame.display.flip()
            clock.tick(60)
            continue

        text = stats.get_stat_text()
        font_img = stats_font.render(text, True, WHITE)
        screen.fill(BLACK)
        all_sprites.draw(screen)
        text_pos = (WINDOW_WIDTH//2 - stats_font.size(text)[0]//2, 20)
        screen.blit(font_img, text_pos)
        pygame.display.flip()

        # update other player over network
        peer.send_state(paddle1, paddle2, ball, stats)

        # target 60fps
        clock.tick(60)


if __name__ == "__main__":
    main()
