import RPi.GPIO as GPIO
import time

# ピン番号はBCM番号で指定
GPIO.setmode(GPIO.BCM)

# 行と列のGPIOピン番号
ROW_PINS = [5, 6, 13, 19]    # R1〜R4
COL_PINS = [12, 16, 20, 21]  # C1〜C4

# キーマップ（4×4）
KEY_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

# GPIO初期化
for row_pin in ROW_PINS:
    GPIO.setup(row_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

for col_pin in COL_PINS:
    GPIO.setup(col_pin, GPIO.OUT)
    GPIO.output(col_pin, GPIO.HIGH)

def read_keypad():
    """押されたキーを1つ検出して返す"""
    for col_idx, col_pin in enumerate(COL_PINS):
        GPIO.output(col_pin, GPIO.LOW)  # この列をアクティブに
        for row_idx, row_pin in enumerate(ROW_PINS):
            if GPIO.input(row_pin) == GPIO.LOW:
                key = KEY_MAP[row_idx][col_idx]
                # 離されるまで待つ（チャタリング防止）
                while GPIO.input(row_pin) == GPIO.LOW:
                    time.sleep(0.02)
                GPIO.output(col_pin, GPIO.HIGH)
                return key
        GPIO.output(col_pin, GPIO.HIGH)
    return None

print("4x4 キーパッドを待機中... (Ctrl+Cで終了)")

try:
    while True:
        key = read_keypad()
        if key:
            print("押下キー:", key)
        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()
    print("\n終了しました")
