#!/usr/bin/env python3
"""Multiplayer maze game server (HTTP + WebSocket)."""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Dict, Optional

import aiohttp
from aiohttp import web


# ===== Config =====
HOST = "0.0.0.0"
PORT = 5000
MAX_PLAYERS_PER_ROOM = 2
MAZE_SEED_BASE = 42
PLAYER_TIMEOUT = 300
CLEANUP_INTERVAL = 60


# ===== Data =====
class Player:
    def __init__(self, player_id: str, ws: web.WebSocketResponse):
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
    def __init__(self, room_id: str, maze_seed: int):
        self.id = room_id
        self.players: Dict[str, Player] = {}
        self.level = 1
        self.maze_seed = maze_seed
        self.created_at = time.time()
        self.game_started = False
        self.winner: Optional[str] = None


# ===== Globals =====
players: Dict[str, Player] = {}
rooms: Dict[str, Room] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ===== Room Helpers =====
def create_room() -> Room:
    room_id = str(uuid.uuid4())[:8]
    maze_seed = MAZE_SEED_BASE + int(time.time()) % 10000
    room = Room(room_id, maze_seed)
    rooms[room_id] = room
    logger.info("[Room] Created room %s", room_id)
    return room


def find_available_room() -> Optional[Room]:
    for room in rooms.values():
        if len(room.players) < MAX_PLAYERS_PER_ROOM and not room.winner:
            return room
    return None


def add_player_to_room(player: Player, room: Room) -> None:
    player.room_id = room.id
    room.players[player.id] = player
    logger.info("[Room] Player %s joined %s (%d players)", player.id, room.id, len(room.players))


def remove_player_from_room(player: Player) -> None:
    if player.room_id and player.room_id in rooms:
        room = rooms[player.room_id]
        if player.id in room.players:
            del room.players[player.id]
            logger.info("[Room] Player %s left %s (%d players)", player.id, room.id, len(room.players))

        if not room.players:
            del rooms[player.room_id]
            logger.info("[Room] Deleted empty room %s", room.id)

    player.room_id = None


# ===== Messaging =====
async def send_to_player(player: Player, message: dict) -> None:
    try:
        if player.ws and not player.ws.closed:
            await player.ws.send_json(message)
    except Exception as exc:
        logger.warning("[Error] Failed to send message: %s", exc)


async def broadcast_to_room(room: Room, message: dict, exclude_player_id: Optional[str] = None) -> None:
    for player_id, player in room.players.items():
        if exclude_player_id and player_id == exclude_player_id:
            continue
        await send_to_player(player, message)


# ===== Message Handlers =====
async def handle_join(player: Player, data: dict) -> None:
    room = find_available_room()
    if room is None:
        room = create_room()

    add_player_to_room(player, room)

    await send_to_player(
        player,
        {
            "type": "joined",
            "player_id": player.id,
            "room_id": room.id,
            "maze_seed": room.maze_seed,
            "level": room.level,
            "players": {
                pid: {"x": p.x, "y": p.y, "z": p.z, "rot_y": p.rot_y}
                for pid, p in room.players.items()
            },
            "is_host": len(room.players) == 1,
        },
    )

    await broadcast_to_room(
        room,
        {
            "type": "player_joined",
            "player_id": player.id,
            "x": player.x,
            "y": player.y,
            "z": player.z,
            "rot_y": player.rot_y,
        },
        exclude_player_id=player.id,
    )

    room.game_started = True


async def handle_update(player: Player, data: dict) -> None:
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

    await broadcast_to_room(
        room,
        {
            "type": "player_update",
            "player_id": player.id,
            "x": player.x,
            "y": player.y,
            "z": player.z,
            "rot_y": player.rot_y,
            "rot_x": player.rot_x,
        },
        exclude_player_id=player.id,
    )


async def handle_attack(player: Player, data: dict) -> None:
    if not player.room_id or player.room_id not in rooms:
        return

    room = rooms[player.room_id]
    await broadcast_to_room(room, {"type": "player_attack", "player_id": player.id}, exclude_player_id=player.id)


async def handle_stun_zombie(player: Player, data: dict) -> None:
    if not player.room_id or player.room_id not in rooms:
        return

    room = rooms[player.room_id]
    await broadcast_to_room(
        room,
        {"type": "zombie_stunned", "zombie_id": data.get("zombie_id"), "by_player": player.id},
        exclude_player_id=player.id,
    )


async def handle_win(player: Player, data: dict) -> None:
    if not player.room_id or player.room_id not in rooms:
        return

    room = rooms[player.room_id]
    if room.winner:
        return

    room.winner = player.id
    logger.info("[Game] Player %s completed level %d in room %s", player.id, room.level, room.id)

    await broadcast_to_room(
        room,
        {
            "type": "level_complete",
            "winner_id": player.id,
            "next_level": room.level + 1,
        },
    )

    await asyncio.sleep(2)

    room.level += 1
    room.maze_seed = MAZE_SEED_BASE + room.level * 1000 + int(time.time()) % 10000
    room.winner = None

    for p in room.players.values():
        p.x = 14.0
        p.y = 1.6
        p.z = 14.0

    await broadcast_to_room(
        room,
        {
            "type": "next_level_start",
            "level": room.level,
            "maze_seed": room.maze_seed,
        },
    )


async def handle_player_hit(player: Player, data: dict) -> None:
    if not player.room_id or player.room_id not in rooms:
        return

    room = rooms[player.room_id]
    player.lives = data.get("lives", player.lives - 1)

    await broadcast_to_room(
        room,
        {"type": "player_hit", "player_id": player.id, "lives": player.lives},
    )


async def handle_game_over(player: Player, data: dict) -> None:
    if not player.room_id or player.room_id not in rooms:
        return

    room = rooms[player.room_id]
    await broadcast_to_room(room, {"type": "game_over", "player_id": player.id})


async def handle_message(player: Player, message: dict) -> None:
    handlers = {
        "join": handle_join,
        "update": handle_update,
        "attack": handle_attack,
        "stun_zombie": handle_stun_zombie,
        "win": handle_win,
        "player_hit": handle_player_hit,
        "game_over": handle_game_over,
    }

    msg_type = message.get("type")
    handler = handlers.get(msg_type)
    if handler:
        await handler(player, message)
    else:
        logger.warning("[Warning] Unknown message type: %s", msg_type)


# ===== HTTP / WebSocket =====
async def handle_http(request: web.Request) -> web.Response:
    try:
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
        with open(html_path, "r", encoding="utf-8") as fp:
            content = fp.read()
        return web.Response(text=content, content_type="text/html")
    except Exception as exc:
        return web.Response(text=f"Error: {exc}", status=500)


async def handle_spa_fallback(request: web.Request) -> web.Response:
    return await handle_http(request)


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    player_id = str(uuid.uuid4())[:8]
    player = Player(player_id, ws)
    players[player_id] = player

    logger.info("[Player] Connected %s", player_id)

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await handle_message(player, data)
                except json.JSONDecodeError:
                    logger.error("[Error] Invalid JSON")
                except Exception as exc:
                    logger.error("[Error] Failed to process message: %s", exc)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error("[Error] WebSocket error: %s", ws.exception())
    except Exception as exc:
        logger.error("[Error] WebSocket exception: %s", exc)
    finally:
        logger.info("[Player] Disconnected %s", player_id)

        if player.room_id and player.room_id in rooms:
            room = rooms[player.room_id]
            await broadcast_to_room(room, {"type": "player_left", "player_id": player_id})

        remove_player_from_room(player)
        players.pop(player_id, None)

    return ws


# ===== Cleanup =====
async def cleanup_inactive_players() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)

        now = time.time()
        stale_ids = []
        for player_id, player in list(players.items()):
            if now - player.last_update > PLAYER_TIMEOUT:
                stale_ids.append(player_id)

        if stale_ids:
            logger.info("[Cleanup] Removing stale players: %s", stale_ids)

        for player_id in stale_ids:
            player = players.get(player_id)
            if player is None:
                continue

            if player.room_id and player.room_id in rooms:
                room = rooms[player.room_id]
                asyncio.create_task(broadcast_to_room(room, {"type": "player_left", "player_id": player_id}))

            remove_player_from_room(player)
            players.pop(player_id, None)

        logger.info("[Status] online players=%d, active rooms=%d", len(players), len(rooms))


async def run_cleanup_task(app: web.Application):
    task = asyncio.create_task(cleanup_inactive_players())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> web.Application:
    app = web.Application()
    app.cleanup_ctx.append(run_cleanup_task)

    app.router.add_get("/", handle_http)
    app.router.add_get("/index.html", handle_http)
    app.router.add_get("/ws", handle_websocket)
    app.router.add_static("/static", os.path.dirname(__file__), name="static")
    app.router.add_get("/{tail:.*}", handle_spa_fallback)
    return app


app = create_app()


if __name__ == "__main__":
    logger.info("[Server] Starting multiplayer game server")
    logger.info("[Server] Listen address: %s:%s", HOST, PORT)
    logger.info("[Server] Max players per room: %d", MAX_PLAYERS_PER_ROOM)
    logger.info("[Server] Open: http://localhost:%s", PORT)
    web.run_app(app, host=HOST, port=PORT)
