"""Live2D 静态资源服务器。"""
import http.server
import socketserver


class ThreadedStaticServer(socketserver.ThreadingTCPServer):
    """浏览器会并行请求动作、纹理和模型资源，必须并发处理连接。"""

    allow_reuse_address = True
    daemon_threads = True
    # 模型启动时会并行请求数十份动作、表情和纹理文件。
    request_queue_size = 128


class StaticHandler(http.server.SimpleHTTPRequestHandler):
    """对入口文件禁用缓存。

    角色管理页切完皮套会写 model_name.js，舞台靠刷新页取新模型；
    OBS 的浏览器源缓存很顽固，入口 HTML 和 model_name.js 必须 no-store，
    否则切了皮套看起来没反应。
    """

    def end_headers(self):
        path = self.path.split("?", 1)[0].lower()
        if path.endswith((".html", "model_name.js", "avatar.json")):
            self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def create_live2d_server(port):
    return ThreadedStaticServer(("", port), StaticHandler)
