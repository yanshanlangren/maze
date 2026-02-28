"""
迷宫躲避陨石游戏 - Python 版本
玩家需要在迷宫中躲避追踪的陨石
"""

import pygame
import random
import math
from collections import deque
from typing import List, Tuple, Set

# 初始化 Pygame
pygame.init()

# 游戏常量
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
CELL_SIZE = 30
MAZE_COLS = WINDOW_WIDTH // CELL_SIZE
MAZE_ROWS = WINDOW_HEIGHT // CELL_SIZE

# 颜色定义
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
ORANGE = (255, 165, 0)
YELLOW = (255, 255, 0)
DARK_GRAY = (40, 40, 40)
LIGHT_BLUE = (135, 206, 250)

class MazeGenerator:
    """使用深度优先搜索算法生成迷宫"""
    
    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        self.maze = [[1 for _ in range(cols)] for _ in range(rows)]
        
    def generate(self) -> List[List[int]]:
        """生成迷宫，1表示墙壁，0表示通道"""
        # 从(1,1)开始生成
        stack = [(1, 1)]
        self.maze[1][1] = 0
        
        directions = [(0, 2), (2, 0), (0, -2), (-2, 0)]
        
        while stack:
            current = stack[-1]
            x, y = current
            
            # 找到所有未访问的邻居
            neighbors = []
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 < nx < self.cols - 1 and 0 < ny < self.rows - 1:
                    if self.maze[ny][nx] == 1:
                        neighbors.append((nx, ny, dx // 2, dy // 2))
            
            if neighbors:
                # 随机选择一个邻居
                nx, ny, dx, dy = random.choice(neighbors)
                # 打通墙壁
                self.maze[y + dy][x + dx] = 0
                self.maze[ny][nx] = 0
                stack.append((nx, ny))
            else:
                stack.pop()
        
        # 增加一些额外的通道，使迷宫不那么复杂
        for _ in range(self.cols * self.rows // 10):
            x = random.randint(1, self.cols - 2)
            y = random.randint(1, self.rows - 2)
            self.maze[y][x] = 0
        
        return self.maze
    
    def find_path(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        """使用BFS找到从start到end的路径"""
        queue = deque([start])
        visited = {start}
        parent = {start: None}
        
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        
        while queue:
            current = queue.popleft()
            
            if current == end:
                # 重建路径
                path = []
                while current:
                    path.append(current)
                    current = parent[current]
                return path[::-1]
            
            for dx, dy in directions:
                nx, ny = current[0] + dx, current[1] + dy
                if (0 <= nx < self.cols and 0 <= ny < self.rows and 
                    self.maze[ny][nx] == 0 and (nx, ny) not in visited):
                    visited.add((nx, ny))
                    parent[(nx, ny)] = current
                    queue.append((nx, ny))
        
        return []


class Player:
    """玩家类"""
    
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.speed = 0.15
        self.lives = 3
        self.invincible_time = 0
        
    def move(self, dx: int, dy: int, maze: List[List[int]]):
        """移动玩家"""
        new_x = self.x + dx * self.speed
        new_y = self.y + dy * self.speed
        
        # 检查碰撞
        cell_x = int(new_x)
        cell_y = int(new_y)
        
        if 0 <= cell_x < len(maze[0]) and 0 <= cell_y < len(maze):
            if maze[cell_y][cell_x] == 0:
                self.x = new_x
                self.y = new_y
    
    def update(self):
        """更新玩家状态"""
        if self.invincible_time > 0:
            self.invincible_time -= 1
    
    def hit(self):
        """玩家被击中"""
        if self.invincible_time <= 0:
            self.lives -= 1
            self.invincible_time = 120  # 2秒无敌时间
            return True
        return False
    
    def draw(self, screen: pygame.Surface):
        """绘制玩家"""
        # 如果无敌，闪烁效果
        if self.invincible_time > 0 and self.invincible_time % 10 < 5:
            return
            
        center_x = int(self.x * CELL_SIZE + CELL_SIZE // 2)
        center_y = int(self.y * CELL_SIZE + CELL_SIZE // 2)
        
        # 绘制玩家（绿色圆形）
        pygame.draw.circle(screen, GREEN, (center_x, center_y), CELL_SIZE // 2 - 2)
        
        # 绘制眼睛
        pygame.draw.circle(screen, WHITE, (center_x - 4, center_y - 3), 4)
        pygame.draw.circle(screen, WHITE, (center_x + 4, center_y - 3), 4)
        pygame.draw.circle(screen, BLACK, (center_x - 4, center_y - 3), 2)
        pygame.draw.circle(screen, BLACK, (center_x + 4, center_y - 3), 2)


class Meteorite:
    """陨石类"""
    
    def __init__(self, x: int, y: int):
        self.x = float(x)
        self.y = float(y)
        self.speed = 0.08  # 比玩家慢一点
        self.path = []
        self.path_update_timer = 0
        self.rotation = 0
        self.trail = []  # 拖尾效果
        
    def update(self, player: Player, maze: List[List[int]], maze_generator: MazeGenerator):
        """更新陨石位置"""
        # 更新路径（每隔一段时间）
        self.path_update_timer += 1
        if self.path_update_timer >= 30 or not self.path:
            self.path_update_timer = 0
            player_cell = (int(player.x), int(player.y))
            meteorite_cell = (int(self.x), int(self.y))
            self.path = maze_generator.find_path(meteorite_cell, player_cell)
        
        # 沿路径移动
        if len(self.path) > 1:
            target = self.path[1]
            dx = target[0] - self.x
            dy = target[1] - self.y
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance > 0:
                self.x += (dx / distance) * self.speed
                self.y += (dy / distance) * self.speed
                
                # 更新旋转
                self.rotation += 5
                
                # 添加拖尾
                self.trail.append((self.x, self.y))
                if len(self.trail) > 10:
                    self.trail.pop(0)
        
        # 检查是否到达路径点
        if len(self.path) > 1:
            target = self.path[1]
            if abs(self.x - target[0]) < 0.1 and abs(self.y - target[1]) < 0.1:
                self.path.pop(0)
    
    def draw(self, screen: pygame.Surface):
        """绘制陨石"""
        # 绘制拖尾
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(255 * (i / len(self.trail)) * 0.3)
            size = int(CELL_SIZE // 2 * (i / len(self.trail)))
            center_x = int(tx * CELL_SIZE + CELL_SIZE // 2)
            center_y = int(ty * CELL_SIZE + CELL_SIZE // 2)
            if size > 0:
                pygame.draw.circle(screen, (255, 100, 0), (center_x, center_y), size)
        
        center_x = int(self.x * CELL_SIZE + CELL_SIZE // 2)
        center_y = int(self.y * CELL_SIZE + CELL_SIZE // 2)
        
        # 绘制陨石主体（不规则多边形）
        points = []
        for i in range(8):
            angle = self.rotation + i * 45
            radius = CELL_SIZE // 2 - 2 + random.randint(-3, 3)
            px = center_x + radius * math.cos(math.radians(angle))
            py = center_y + radius * math.sin(math.radians(angle))
            points.append((px, py))
        
        pygame.draw.polygon(screen, ORANGE, points)
        pygame.draw.polygon(screen, RED, points, 2)
        
        # 绘制火焰效果
        for _ in range(3):
            flame_x = center_x + random.randint(-5, 5)
            flame_y = center_y + random.randint(-5, 5)
            pygame.draw.circle(screen, YELLOW, (flame_x, flame_y), 3)
    
    def check_collision(self, player: Player) -> bool:
        """检查是否与玩家碰撞"""
        distance = math.sqrt((self.x - player.x) ** 2 + (self.y - player.y) ** 2)
        return distance < 0.8


class Game:
    """游戏主类"""
    
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("迷宫躲避陨石 - Maze Meteorite Escape")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.big_font = pygame.font.Font(None, 72)
        
        self.maze_generator = MazeGenerator(MAZE_COLS, MAZE_ROWS)
        self.reset_game()
        
    def reset_game(self):
        """重置游戏"""
        # 生成迷宫
        self.maze = self.maze_generator.generate()
        
        # 找到一个空位置放置玩家
        self.player = None
        for y in range(1, MAZE_ROWS - 1):
            for x in range(1, MAZE_COLS - 1):
                if self.maze[y][x] == 0:
                    self.player = Player(x, y)
                    break
            if self.player:
                break
        
        # 创建陨石（从迷宫边缘开始）
        self.meteorites = []
        for _ in range(3):  # 初始3个陨石
            self.spawn_meteorite()
        
        self.score = 0
        self.game_over = False
        self.survival_time = 0
        self.difficulty_timer = 0
        
    def spawn_meteorite(self):
        """在随机位置生成陨石"""
        attempts = 0
        while attempts < 100:
            x = random.randint(1, MAZE_COLS - 2)
            y = random.randint(1, MAZE_ROWS - 2)
            
            # 确保不在玩家附近
            if self.maze[y][x] == 0:
                distance = math.sqrt((x - self.player.x) ** 2 + (y - self.player.y) ** 2)
                if distance > 10:  # 至少距离玩家10格
                    self.meteorites.append(Meteorite(x, y))
                    return
            attempts += 1
    
    def handle_events(self) -> bool:
        """处理事件，返回False表示退出游戏"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r and self.game_over:
                    self.reset_game()
        return True
    
    def update(self):
        """更新游戏状态"""
        if self.game_over:
            return
        
        # 获取按键状态
        keys = pygame.key.get_pressed()
        
        dx, dy = 0, 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx = -1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx = 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy = -1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy = 1
        
        # 移动玩家
        if dx != 0 or dy != 0:
            self.player.move(dx, dy, self.maze)
        
        # 更新玩家
        self.player.update()
        
        # 更新陨石
        for meteorite in self.meteorites:
            meteorite.update(self.player, self.maze, self.maze_generator)
            
            # 检查碰撞
            if meteorite.check_collision(self.player):
                if self.player.hit():
                    # 玩家被击中，将陨石推开
                    meteorite.x -= (meteorite.x - self.player.x) * 2
                    meteorite.y -= (meteorite.y - self.player.y) * 2
                    meteorite.path = []
                    
                    if self.player.lives <= 0:
                        self.game_over = True
        
        # 更新分数和难度
        self.survival_time += 1
        self.score = self.survival_time // 60  # 每秒得1分
        
        # 每30秒增加一个陨石
        self.difficulty_timer += 1
        if self.difficulty_timer >= 1800:  # 30秒
            self.difficulty_timer = 0
            self.spawn_meteorite()
    
    def draw(self):
        """绘制游戏画面"""
        # 绘制背景
        self.screen.fill(DARK_GRAY)
        
        # 绘制迷宫
        for y in range(MAZE_ROWS):
            for x in range(MAZE_COLS):
                if self.maze[y][x] == 1:
                    rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    pygame.draw.rect(self.screen, (60, 60, 80), rect)
                    pygame.draw.rect(self.screen, (80, 80, 100), rect, 1)
        
        # 绘制陨石
        for meteorite in self.meteorites:
            meteorite.draw(self.screen)
        
        # 绘制玩家
        self.player.draw(self.screen)
        
        # 绘制UI
        self.draw_ui()
        
        pygame.display.flip()
    
    def draw_ui(self):
        """绘制用户界面"""
        # 绘制分数
        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        self.screen.blit(score_text, (10, 10))
        
        # 绘制生命值
        lives_text = self.font.render(f"Lives: {self.player.lives}", True, WHITE)
        self.screen.blit(lives_text, (10, 50))
        
        # 绘制陨石数量
        meteor_text = self.font.render(f"Meteors: {len(self.meteorites)}", True, ORANGE)
        self.screen.blit(meteor_text, (10, 90))
        
        # 游戏结束画面
        if self.game_over:
            # 半透明遮罩
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
            overlay.set_alpha(128)
            overlay.fill(BLACK)
            self.screen.blit(overlay, (0, 0))
            
            # 游戏结束文字
            game_over_text = self.big_font.render("GAME OVER", True, RED)
            text_rect = game_over_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 50))
            self.screen.blit(game_over_text, text_rect)
            
            # 最终分数
            final_score_text = self.font.render(f"Final Score: {self.score}", True, WHITE)
            score_rect = final_score_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 20))
            self.screen.blit(final_score_text, score_rect)
            
            # 重新开始提示
            restart_text = self.font.render("Press R to Restart", True, YELLOW)
            restart_rect = restart_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 70))
            self.screen.blit(restart_text, restart_rect)
    
    def run(self):
        """运行游戏主循环"""
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)
        
        pygame.quit()


def main():
    """主函数"""
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
