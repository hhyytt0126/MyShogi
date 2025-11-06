import ctypes
import time
import cdio
import sys
from utils import get_single_set_bit
DEV_NAME_IN = "DIO000"
KEY_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]
# 初期化
dio_id_in = ctypes.c_short()
err_str = ctypes.create_string_buffer(256)
def get_key(value):
    """
    value: Dioからの1バイト入力
    返り値: 押されたキー文字、または None
    """
    row, col = get_single_set_bit(value)
    if row is not None and col is not None:
        return KEY_MAP[row][col]
    return None
ret = cdio.DioInit(DEV_NAME_IN.encode(), ctypes.byref(dio_id_in))
if ret != cdio.DIO_ERR_SUCCESS:
    cdio.DioGetErrorString(ret, err_str)
    print("入力初期化エラー:", err_str.value.decode())
    sys.exit(1)

print("4bit分割表示開始 (Ctrl+Cで終了)")

try:
    while True:
        in_data = ctypes.c_ubyte()
        ret = cdio.DioInpByte(dio_id_in, ctypes.c_short(0), ctypes.byref(in_data))

        if ret == cdio.DIO_ERR_SUCCESS:
            value = in_data.value
            key = get_key(value)
            if(key == None):
                time.sleep(0.1)
                continue
            print(key)
        else:
            print("読み取りエラー")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n終了します...")
    cdio.DioExit(dio_id_in)
