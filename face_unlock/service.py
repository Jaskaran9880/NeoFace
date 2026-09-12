import json
import win32pipe
import win32file


PIPE = r"\\.\pipe\NeoFace"


def serve_loop(on_msg):
    while True:
        pipe = win32pipe.CreateNamedPipe(
            PIPE,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_WAIT,
            1, 65536, 65536, 0, None,
        )
        win32pipe.ConnectNamedPipe(pipe, None)
        try:
            _, data = win32file.ReadFile(pipe, 65536)
            req = json.loads(data.decode("utf-8"))
            resp = on_msg(req)
            win32file.WriteFile(pipe, json.dumps(resp).encode("utf-8"))
        finally:
            win32file.CloseHandle(pipe)
