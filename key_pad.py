"""Keypad module with safe behavior when RPi.GPIO is not available.

Provides:
- register_callback(fn) / unregister_callback(fn)
- start_polling() / stop_polling()
- simulate_key(key) for desktop testing
"""
import time
import threading

# Minimum milliseconds to ignore repeated identical key events (rate-limit)
MIN_REPEAT_MS = 300

# Try to import RPi.GPIO; if not available, run in mock mode
try:
    import RPi.GPIO as GPIO  # type: ignore
    _GPIO_AVAILABLE = True
except Exception:
    GPIO = None
    _GPIO_AVAILABLE = False

# 行と列のGPIOピン番号 (BCM)
ROW_PINS = [5, 6, 13, 19]    # R1〜R4
COL_PINS = [12, 16, 20, 21]  # C1〜C4

# キーマップ（4×4）
KEY_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

# GPIO初期化は実機時のみ行う
if _GPIO_AVAILABLE:
    try:
        GPIO.setmode(GPIO.BCM)
        for row_pin in ROW_PINS:
            GPIO.setup(row_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        for col_pin in COL_PINS:
            GPIO.setup(col_pin, GPIO.OUT)
            GPIO.output(col_pin, GPIO.HIGH)
    except Exception:
        # 初期化に失敗しても継続（上位でハンドリング）
        _GPIO_AVAILABLE = False

# コールバック管理
_callbacks = []
_poll_thread = None
_poll_thread_stop = False
_last_key = None
_last_time = 0.0
_poll_lock = threading.Lock()

def register_callback(fn):
    """Register a callback fn(key: str) to be called on key press."""
    if fn not in _callbacks:
        _callbacks.append(fn)
        try:
            print(f"[key_pad] callback registered: {getattr(fn, '__name__', repr(fn))}")
        except Exception:
            pass
    try:
        print(f"[key_pad] callbacks count: {len(_callbacks)}")
    except Exception:
        pass

def unregister_callback(fn):
    """Unregister a previously registered callback."""
    try:
        _callbacks.remove(fn)
        try:
            print(f"[key_pad] callback unregistered: {getattr(fn, '__name__', repr(fn))}")
        except Exception:
            pass
        try:
            print(f"[key_pad] callbacks count: {len(_callbacks)}")
        except Exception:
            pass
    except ValueError:
        pass

def unregister_all():
    """Unregister all callbacks (force-clean)."""
    try:
        _callbacks.clear()
        try:
            print("[key_pad] all callbacks unregistered")
        except Exception:
            pass
    except Exception:
        pass

def _notify(key: str):
    # Print the key for debug/visibility
    global _last_key, _last_time
    try:
        now = time.time()
        # Suppress rapid repeated same-key events (rate-limit)
        if _last_key is not None and key == _last_key and (now - _last_time) < (MIN_REPEAT_MS / 1000.0):
            # update last seen timestamp but do not notify callbacks
            _last_time = now
            return
        # simple debounce/ghosting suppression: if a different key arrives within 80ms, ignore it
        if _last_key is not None and (now - _last_time) < 0.08 and key != _last_key:
            # update last seen but do not notify callbacks
            _last_key = key
            _last_time = now
            return
        _last_key = key
        _last_time = now
    except Exception:
        pass
    for cb in list(_callbacks):
        try:
            cb(key)
        except Exception:
            # Ignore exceptions from callbacks to keep polling stable
            pass

def read_keypad():
    """Read one key from the physical keypad. Returns None when no key or GPIO unavailable."""
    if not _GPIO_AVAILABLE:
        return None
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

def _poll_loop():
    global _poll_thread_stop
    while not _poll_thread_stop:
        try:
            key = read_keypad()
            if key:
                _notify(key)
        except Exception:
            # ignore and continue
            pass
        time.sleep(0.05)

def start_polling():
    """Start background polling thread. Safe to call on non-RPi (no-op)."""
    global _poll_thread, _poll_thread_stop
    try:
        print(f"[key_pad] start_polling called (GPIO available: {_GPIO_AVAILABLE})")
    except Exception:
        pass
    if not _GPIO_AVAILABLE:
        return
    with _poll_lock:
        if _poll_thread and _poll_thread.is_alive():
            return
        _poll_thread_stop = False
        _poll_thread = threading.Thread(target=_poll_loop, daemon=True)
        _poll_thread.start()

def stop_polling():
    """Stop the background polling thread."""
    global _poll_thread_stop, _poll_thread
    try:
        print(f"[key_pad] stop_polling called")
    except Exception:
        pass
    # Signal the loop to stop and wait for the thread to exit.
    with _poll_lock:
        _poll_thread_stop = True
        try:
            t = _poll_thread
            if t and t.is_alive():
                try:
                    t.join(timeout=2.0)
                except Exception:
                    pass
        finally:
            _poll_thread = None

def simulate_key(key: str):
    """Simulate/inject a key event (useful for desktop testing)."""
    _notify(key)

def main():
    """Standalone behavior for testing the module."""
    if not _GPIO_AVAILABLE:
        print("RPi.GPIO not available — run in mock mode. Use simulate_key() to test.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n終了しました")
        return

    print("4x4 キーパッドを待機中... (Ctrl+Cで終了)")
    start_polling()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_polling()
        try:
            GPIO.cleanup()
        except Exception:
            pass
        print("\n終了しました")


if __name__ == "__main__":
    main()
