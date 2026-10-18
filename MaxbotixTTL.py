"""Read framed Maxbotix TTL distance values; return millimetres."""
import time

def startSerial():
    from serial import Serial
    return Serial('/dev/ttyS0', 9600, 8, 'N', 1, timeout=0.2)

def measure(serialCom, timeout=3):
    deadline = time.monotonic() + timeout
    frame = bytearray()
    started = False
    while time.monotonic() < deadline:
        byte = serialCom.read(1)
        if byte == b'R':
            frame.clear()
            started = True
        elif byte == b'\r':
            if started and frame and frame.isdigit():
                return int(frame)
            frame.clear()
            started = False
        elif started and byte and byte.isdigit():
            frame.extend(byte)
            if len(frame) > 6:
                frame.clear()
                started = False
        elif byte:
            frame.clear()
            started = False
    raise TimeoutError('No valid Maxbotix frame before deadline')

if __name__ == '__main__':
    with startSerial() as port:
        print(measure(port))
