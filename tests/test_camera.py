import win32file, win32pipe, time

PIPE = r'\\.\pipe\NeoFace'
print(f"Connecting to {PIPE}...")
try:
    h = win32file.CreateFile(PIPE, 0x80000000 | 0x40000000, 0, None, 3, 0, None)
    print(f"Connected!")
except Exception as e:
    print(f"FAILED: {e}")
    exit(1)

mode = win32pipe.PIPE_READMODE_MESSAGE
win32pipe.SetNamedPipeHandleState(h, mode, None, None)

print("Sending VERIFY perve... Camera LED should flash NOW!")
msg = b'VERIFY perve\x00'
win32file.WriteFile(h, msg)

print("Waiting for response (up to 30s)...")
try:
    hr, data = win32file.ReadFile(h, 1024)
    print(f"Response: {data}")
except Exception as e:
    print(f"Read failed: {e}")

win32file.CloseHandle(h)
