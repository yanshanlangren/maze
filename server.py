"""
简单的 HTTP 服务器，用于提供游戏预览页面
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

class GameHandler(SimpleHTTPRequestHandler):
    """自定义处理器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/workspace/projects", **kwargs)
    
    def end_headers(self):
        # 添加 CORS 头
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

def main():
    """启动服务器"""
    port = 5000
    server = HTTPServer(('0.0.0.0', port), GameHandler)
    print(f"🎮 游戏服务器运行在 http://localhost:{port}")
    print("📋 使用说明:")
    print("   - 在浏览器中打开上述地址即可预览游戏")
    print("   - 下载 game.py 在本地运行可获得完整体验")
    print("   - 按 Ctrl+C 停止服务器")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.shutdown()

if __name__ == "__main__":
    main()
