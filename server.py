#!/usr/bin/env python3
"""
3D迷宫逃脱 - 多人游戏服务器
支持房间系统，每房间最多2人
使用 aiohttp 同时处理 HTTP 和 WebSocket
"""

import asyncio
import json
import uuid
import time
import os
from typing import Dict, Optional
from aiohttp import web
import aiohttp

# ========== 配置 ==========
HOST = "0.0.0.0"
PORT = 5000
MAX_PLAYERS_PER_ROOM = 2
MAZE_SEED_BASE = 42

# ========== 数据结构 ==========
class Player:
    """玩家数据"""
    def __init__(self, player_id: str, ws):
        self.id = player_id
        self.ws = ws
        self.room_id: Optional[str] = None
        self.x = 14.0
        self.y = 1.6
        self.z = 14.0
        self.rot_y = 0.0
        self.rot_x = 0.0
        self.lives = 3
        self.level = 1
        self.connected = True
        self.last_update = time.time()

class Room:
    """游戏房间"""
    def __init__(self, room_id: str, maze_seed: int):
        self.id = room_id
        self.players: Dict[str, Player] = {}
        self.level = 1
        self.maze_seed = maze_seed
        self.created_at = time.time()
        self.game_started = False
        self.winner: Optional[str] = None

# ========== 全局状态 ==========
players: Dict[str, Player] = {}
rooms: Dict[str, Room] = {}

# ========== 房间管理 ==========
def create_room() -> Room:
    """创建新房间"""
    room_id = str(uuid.uuid4())[:8]
    maze_seed = MAZE_SEED_BASE + int(time.time()) % 10000
    room = Room(room_id, maze_seed)
    rooms[room_id] = room
    print(f"[Room] 创建新房间: {room_id}")
    return room

def find_available_room() -> Optional[Room]:
    """查找可用房间"""
    for room in rooms.values():
        if len(room.players) < MAX_PLAYERS_PER_ROOM and not room.winner:
            return room
    return None

def add_player_to_room(player: Player, room: Room):
    """将玩家加入房间"""
    player.room_id = room.id
    room.players[player.id] = player
    print(f"[Room] 玩家 {player.id} 加入房间 {room.id}, 当前人数: {len(room.players)}")

def remove_player_from_room(player: Player):
    """将玩家移出房间"""
    if player.room_id and player.room_id in rooms:
        room = rooms[player.room_id]
        if player.id in room.players:
            del room.players[player.id]
            print(f"[Room] 玩家 {player.id} 离开房间 {room.id}, 剩余人数: {len(room.players)}")
        
        if len(room.players) == 0:
            del rooms[player.room_id]
            print(f"[Room] 删除空房间: {room.id}")
    
    player.room_id = None

# ========== 消息发送 ==========
async def send_to_player(player: Player, message: dict):
    """发送消息给单个玩家"""
    try:
        await player.ws.send_json(message)
    except Exception as e:
        print(f"[Error] 发送消息失败: {e}")

async def broadcast_to_room(room: Room, message: dict, exclude_player_id: Optional[str] = None):
    """广播消息给房间内所有玩家"""
    for player_id, player in room.players.items():
        if exclude_player_id and player_id == exclude_player_id:
            continue
        await send_to_player(player, message)

# ========== 消息处理 ==========
async def handle_join(player: Player, data: dict):
    """处理玩家加入"""
    room = find_available_room()
    if not room:
        room = create_room()
    
    add_player_to_room(player, room)
    
    await send_to_player(player, {
        "type": "joined",
        "player_id": player.id,
        "room_id": room.id,
        "maze_seed": room.maze_seed,
        "level": room.level,
        "players": {pid: {"x": p.x, "y": p.y, "z": p.z, "rot_y": p.rot_y} 
                   for pid, p in room.players.items()},
        "is_host": len(room.players) == 1
    })
    
    await broadcast_to_room(room, {
        "type": "player_joined",
        "player_id": player.id,
        "x": player.x,
        "y": player.y,
        "z": player.z,
        "rot_y": player.rot_y
    }, exclude_player_id=player.id)
    
    if len(room.players) == MAX_PLAYERS_PER_ROOM:
        room.game_started = True
        await broadcast_to_room(room, {
            "type": "game_start",
            "level": room.level
        })

async def handle_update(player: Player, data: dict):
    """处理玩家状态更新"""
    if not player.room_id or player.room_id not in rooms:
        return
    
    room = rooms[player.room_id]
    
    player.x = data.get("x", player.x)
    player.y = data.get("y", player.y)
    player.z = data.get("z", player.z)
    player.rot_y = data.get("rot_y", player.rot_y)
    player.rot_x = data.get("rot_x", player.rot_x)
    player.lives = data.get("lives", player.lives)
    player.last_update = time.time()
    
    await broadcast_to_room(room, {
        "type": "player_update",
        "player_id": player.id,
        "x": player.x,
        "y": player.y,
        "z": player.z,
        "rot_y": player.rot_y,
        "rot_x": player.rot_x
    }, exclude_player_id=player.id)

async def handle_attack(player: Player, data: dict):
    """处理攻击事件"""
    if not player.room_id or player.room_id not in rooms:
        return
    
    room = rooms[player.room_id]
    
    await broadcast_to_room(room, {
        "type": "player_attack",
        "player_id": player.id
    }, exclude_player_id=player.id)

async def handle_stun_zombie(player: Player, data: dict):
    """处理僵尸被击晕"""
    if not player.room_id or player.room_id not in rooms:
        return
    
    room = rooms[player.room_id]
    
    await broadcast_to_room(room, {
        "type": "zombie_stunned",
        "zombie_id": data.get("zombie_id"),
        "by_player": player.id
    }, exclude_player_id=player.id)

async def handle_win(player: Player, data: dict):
    """处理玩家通关"""
    if not player.room_id or player.room_id not in rooms:
        return
    
    room = rooms[player.room_id]
    
    if room.winner:
        return
    
    room.winner = player.id
    print(f"[Game] 玩家 {player.id} 在房间 {room.id} 通关关卡 {room.level}")
    
    await broadcast_to_room(room, {
        "type": "level_complete",
        "winner_id": player.id,
        "next_level": room.level + 1
    })
    
    # 准备下一关
    await asyncio.sleep(2)  # 等待动画
    
    room.level += 1
    room.maze_seed = MAZE_SEED_BASE + room.level * 1000 + int(time.time()) % 10000
    room.winner = None
    
    for p in room.players.values():
        p.x = 14.0
        p.y = 1.6
        p.z = 14.0
    
    # 通知开始下一关
    await broadcast_to_room(room, {
        "type": "next_level_start",
        "level": room.level,
        "maze_seed": room.maze_seed
    })

async def handle_player_hit(player: Player, data: dict):
    """处理玩家受伤"""
    if not player.room_id or player.room_id not in rooms:
        return
    
    room = rooms[player.room_id]
    player.lives = data.get("lives", player.lives - 1)
    
    await broadcast_to_room(room, {
        "type": "player_hit",
        "player_id": player.id,
        "lives": player.lives
    })

async def handle_game_over(player: Player, data: dict):
    """处理游戏结束"""
    if not player.room_id or player.room_id not in rooms:
        return
    
    room = rooms[player.room_id]
    
    await broadcast_to_room(room, {
        "type": "game_over",
        "player_id": player.id
    })

async def handle_message(player: Player, message: dict):
    """处理客户端消息"""
    msg_type = message.get("type")
    
    handlers = {
        "join": handle_join,
        "update": handle_update,
        "attack": handle_attack,
        "stun_zombie": handle_stun_zombie,
        "win": handle_win,
        "player_hit": handle_player_hit,
        "game_over": handle_game_over,
    }
    
    handler = handlers.get(msg_type)
    if handler:
        await handler(player, message)
    else:
        print(f"[Warning] 未知消息类型: {msg_type}")

# ========== HTTP 和 WebSocket 处理 ==========
async def handle_http(request: web.Request) -> web.Response:
    """处理 HTTP 请求，返回 HTML 页面"""
    try:
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.Response(text=content, content_type="text/html")
    except Exception as e:
        return web.Response(text=f"Error: {e}", status=500)

async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    """处理 WebSocket 连接"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    player_id = str(uuid.uuid4())[:8]
    player = Player(player_id, ws)
    players[player_id] = player
    
    print(f"[Player] 新连接: {player_id}")
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await handle_message(player, data)
                except json.JSONDecodeError:
                    print(f"[Error] 无效的 JSON 消息")
                except Exception as e:
                    print(f"[Error] 处理消息失败: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f"[Error] WebSocket 错误: {ws.exception()}")
    except Exception as e:
        print(f"[Error] WebSocket 异常: {e}")
    finally:
        print(f"[Player] 连接关闭: {player_id}")
        
        if player.room_id and player.room_id in rooms:
            room = rooms[player.room_id]
            await broadcast_to_room(room, {
                "type": "player_left",
                "player_id": player_id
            })
        
        remove_player_from_room(player)
        if player_id in players:
            del players[player_id]
    
    return ws

# ========== 应用配置 ==========
app = web.Application()

# 路由
app.router.add_get("/", handle_http)
app.router.add_get("/index.html", handle_http)
app.router.add_get("/ws", handle_websocket)

# 静态文件（如果有）
app.router.add_static("/static", os.path.dirname(__file__), name="static")

# ========== 主函数 ==========
if __name__ == "__main__":
    print(f"[Server] 多人游戏服务器启动")
    print(f"[Server] 端口: {PORT}")
    print(f"[Server] 每房间最大玩家数: {MAX_PLAYERS_PER_ROOM}")
    print(f"[Server] 访问地址: http://localhost:{PORT}")
    
    web.run_app(app, host=HOST, port=PORT)
