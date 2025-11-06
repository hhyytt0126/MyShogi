import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from kiki import get_koma_kiki_sfen
import threading
import time
import urllib.parse
import urllib.request
import json
import re

# --- 設定 ---
BOARD_SIZE = 9
CELL_SIZE = 64
# UI layout constants
KOMADAI_HEIGHT = 100  # top and bottom piece-stand height
PANEL_HEIGHT = 180    # bottom control panel height
PIECE_SPRITE = "NR4.png"
BOARD_IMAGE = "V01.png"
KOMADAI_IMAGE = "Y1.png"  # 持ち駒台画像
SPRITE_ROWS = 4
SPRITE_COLS = 8
AI_ENDPOINT = "https://17xn1ovxga.execute-api.ap-northeast-1.amazonaws.com/production/gikou"

initial_sfen = [
    "lnsgkgsnl",
    "1r5b1",
    "ppppppppp",
    "9",
    "9",
    "9",
    "PPPPPPPPP",
    "1B5R1",
    "LNSGKGSNL"
]

def sfen_to_board(sfen_rows):
    board = []
    for row in sfen_rows:
        board_row = []
        i = 0
        while i < len(row):
            if row[i].isdigit():
                board_row.extend([""] * int(row[i]))
                i += 1
            elif row[i] == '+':
                board_row.append('+' + row[i+1])
                i += 2
            else:
                board_row.append(row[i])
                i += 1
        board.append(board_row)
    return board

PIECE_COL_MAP = {
    "K": (0, 0), "R": (1, 0), "B": (2, 0), "G": (3, 0),
    "S": (4, 0), "N": (5, 0), "L": (6, 0), "P": (7, 0),
    "+R": (1, 1), "+B": (2, 1), "+S": (4, 1), "+N": (5, 1), "+L": (6, 1), "+P": (7, 1),
    "k": (0, 2), "r": (1, 2), "b": (2, 2), "g": (3, 2),
    "s": (4, 2), "n": (5, 2), "l": (6, 2), "p": (7, 2),
    "+r": (1, 3), "+b": (2, 3), "+s": (4, 3), "+n": (5, 3), "+l": (6, 3), "+p": (7, 3)
}

class ShogiApp:
    def __init__(self, root, ai_enabled: bool = False, ai_side: str = '後手', ai_byoyomi_ms: int = 2000):
        self.root = root
        self.root.title("将棋（持ち駒対応）")

        # --- 全体キャンバスサイズ（持ち駒台を含む） ---
        self.top_offset = KOMADAI_HEIGHT 
        self.board_height = BOARD_SIZE * CELL_SIZE
        self.bottom_komadai_y0 = self.top_offset + self.board_height
        self.panel_y0 = self.bottom_komadai_y0 + KOMADAI_HEIGHT
        self.total_height = self.panel_y0 + PANEL_HEIGHT

        self.canvas = tk.Canvas(root, width=BOARD_SIZE*CELL_SIZE, height=self.total_height)
        self.canvas.pack()

        # --- 背景画像（盤面） ---
        self.board_img = Image.open(BOARD_IMAGE)
        self.board_img = self.board_img.resize((BOARD_SIZE*CELL_SIZE, BOARD_SIZE*CELL_SIZE))
        self.board_texture = ImageTk.PhotoImage(self.board_img)
        self.canvas.create_image(0, self.top_offset, anchor=tk.NW, image=self.board_texture)

        # --- 駒台画像 ---
        self.komadai_img = Image.open(KOMADAI_IMAGE)
        self.komadai_img = self.komadai_img.resize((BOARD_SIZE*CELL_SIZE, KOMADAI_HEIGHT))
        self.komadai_texture = ImageTk.PhotoImage(self.komadai_img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.komadai_texture)  # 上側の駒台
        self.canvas.create_image(0, self.bottom_komadai_y0, anchor=tk.NW, image=self.komadai_texture)  # 下側の駒台

        # --- 下部パネル背景 ---
        self.panel_bg_id = self.canvas.create_rectangle(
            0, self.panel_y0, BOARD_SIZE*CELL_SIZE, self.total_height,
            fill="#f0f0f0", outline=""
        )

        # --- 盤面線 ---
        for i in range(BOARD_SIZE + 1):
            x = i * CELL_SIZE
            y = i * CELL_SIZE + self.top_offset
            self.canvas.create_line(x, self.top_offset, x, self.top_offset + BOARD_SIZE*CELL_SIZE, fill="#000", width=2)
            self.canvas.create_line(0, y, BOARD_SIZE*CELL_SIZE, y, fill="#000", width=2)

        # --- スプライト読み込み ---
        self.sprite = Image.open(PIECE_SPRITE)
        self.sprite_width = self.sprite.width // SPRITE_COLS
        self.sprite_height = self.sprite.height // SPRITE_ROWS
        self.piece_images = {}
        self.load_pieces()

        # --- 状態 ---
        self.board = sfen_to_board(initial_sfen)
        self.piece_ids = [[None]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.selected = None
        self.selected_captured = None  # 選択された持ち駒 (piece, index)
        self.turn = "先手"
        self.kiki_list = []  # 現在の利きリスト
        self.pending_move = None  # 成り選択待ちの移動 (sr, sc, r, c, piece, target)
        self.promotion_widget_ids = []  # キャンバス上の成りUIウィジェットIDs
        self._promotion_imgs = {}  # 成/不成ボタン用の画像参照保持
        self.game_over = False
        self.result_widget_ids = []
        # --- AI設定 ---
        self.ai_enabled = ai_enabled
        self.ai_side = ai_side  # '先手' or '後手'
        self.ai_byoyomi_ms = ai_byoyomi_ms
        self.ai_thinking = False
        self.ai_status_id = None

        # --- 棋譜（局面）履歴 ---
        self.history = []           # 各要素: dict(board, sente_caps, gote_caps, turn)
        self.history_index = -1     # 現在指している局面のインデックス

        # --- 持ち駒リスト ---
        self.captured_by_sente = []  # 先手が取った駒
        self.captured_by_gote = []   # 後手が取った駒

        # --- ヒント機能 ---
        self.hint_arrow_id = None  # ヒント矢印のID

        self.draw_pieces()
        self.canvas.bind("<Button-1>", self.on_click)

        # レビュー用コントロール作成 & 初期局面保存
        self.create_review_controls()
        self.create_game_control_buttons()
        
        # --- Keypad（物理キーパッド）からの操作対応 ---
        # カーソル位置（盤上の行・列）を初期化（中央）
        self.kp_r = BOARD_SIZE // 2
        self.kp_c = BOARD_SIZE // 2
        # 初期表示
        try:
            self.draw_keypad_cursor()
        except Exception:
            pass
        # 描画しておく（メソッドはクラス内で定義）
        try:
            # Prefer callback-based integration using key_pad module
            import key_pad

            # start polling if supported (no-op on non-RPi)
            try:
                key_pad.start_polling()
                try:
                    print(f"[shogi] key_pad.start_polling called")
                except Exception:
                    pass
            except Exception:
                pass

            def _on_keypad_key(key):
                if not key:
                    return
                # 5 = confirm
                if key == '5':
                    self.root.after(0, lambda: self.keypad_confirm())
                    return
                # Invert vertical direction: keypad '8' should move down and '2' should move up
                moves = {
                    '8': (1, 0),   # down (was up)
                    '2': (-1, 0),  # up (was down)
                    '4': (0, -1),  # left
                    '6': (0, 1),   # right
                    '7': (1, -1),  # down-left (was up-left)
                    '9': (1, 1),   # down-right (was up-right)
                    '1': (-1, -1), # up-left (was down-left)
                    '3': (-1, 1),  # up-right (was down-right)
                }
                if key in moves:
                    dr, dc = moves[key]
                    self.root.after(0, lambda dr=dr, dc=dc: self.move_keypad_cursor(dr, dc))

            try:
                key_pad.register_callback(_on_keypad_key)
                self._keypad_cb = _on_keypad_key
                try:
                    print(f"[shogi] keypad callback registered: {_on_keypad_key.__name__}")
                except Exception:
                    pass
            except Exception:
                self._keypad_cb = None
        except Exception:
            self._keypad_cb = None
        
    def create_game_control_buttons(self):
        # 下部パネルに「ホームへ戻る」「ヒント」「降参」ボタンを中央揃えで横に配置
        btn_opts = dict(font=("Meiryo", 10), width=10)
        center_x = BOARD_SIZE * CELL_SIZE // 2
        y = self.panel_y0 + 110
        x_spacing = 100
        self.btn_home = tk.Button(self.root, text="ホームへ戻る", command=self.go_home, **btn_opts)
        self.btn_hint = tk.Button(self.root, text="ヒント", command=self.show_hint, **btn_opts)
        self.btn_resign = tk.Button(self.root, text="降参", command=self.resign_game, **btn_opts)
        self.canvas.create_window(center_x - x_spacing, y, window=self.btn_home)
        self.canvas.create_window(center_x, y, window=self.btn_hint)
        self.canvas.create_window(center_x + x_spacing, y, window=self.btn_resign)

    def go_home(self):
        # 盤面UIを破棄してホーム画面へ
        # unregister keypad callback if any
        try:
            import key_pad
            if getattr(self, '_keypad_cb', None):
                try:
                    key_pad.unregister_callback(self._keypad_cb)
                    try:
                        print(f"[shogi] keypad callback unregistered")
                    except Exception:
                        pass
                except Exception:
                    pass
            try:
                key_pad.stop_polling()
                try:
                    print(f"[shogi] key_pad.stop_polling called")
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
        self.canvas.destroy()
        try:
            self.btn_home.destroy()
            self.btn_resign.destroy()
            self.btn_hint.destroy()
            self.btn_first.destroy()
            self.btn_prev.destroy()
            self.btn_next.destroy()
            self.btn_last.destroy()
        except Exception:
            pass
        from home import HomeApp
        HomeApp(self.root)

    def resign_game(self):
        if getattr(self, 'game_over', False):
            return
        winner = '後手' if self.turn == '先手' else '先手'
        self.show_result(winner, resign=True)
        self.save_history(truncate_future=False)  # 初期局面を保存
        # キーバインド（Undo/レビュー移動）
        self.root.bind('<Left>', lambda e: self.go_prev())
        self.root.bind('<Right>', lambda e: self.go_next())
        self.root.bind('<Home>', lambda e: self.go_first())
        self.root.bind('<End>', lambda e: self.go_last())
        self.root.bind('<Control-z>', lambda e: self.go_prev())

        # 先手がAIなら初手を思考
        self.schedule_ai_move_if_needed()

    def show_hint(self):
        """AIに最善手を聞いてヒント矢印を表示"""
        if getattr(self, 'game_over', False):
            return
        if getattr(self, 'ai_thinking', False):
            return
        if self.is_review_mode():
            return
        
        # 既存のヒント矢印を削除
        self.clear_hint_arrow()
        
        # AIに最善手を問い合わせ（非同期）
        def fetch_hint():
            try:
                sfen = self.board_to_sfen()
                print(f"Hint: Sending SFEN to AI: {sfen}")
                params = {
                    'position': f'sfen {sfen}',
                    'byoyomi': '1000'  # ヒントは短時間で
                }
                url = AI_ENDPOINT + '?' + urllib.parse.urlencode(params)
                with urllib.request.urlopen(url, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    bestmove = data.get('bestmove', '')
                    print(f"Hint: Received bestmove: {bestmove}")
                    
                    if bestmove and bestmove != 'resign':
                        # 移動元と移動先を解析
                        from_pos, to_pos = self.parse_usi_move(bestmove)
                        if from_pos and to_pos:
                            # メインスレッドで矢印を描画
                            self.root.after(0, lambda: self.draw_hint_arrow(from_pos, to_pos))
            except Exception as e:
                print(f"Hint error: {e}")
        
        # 別スレッドで実行
        threading.Thread(target=fetch_hint, daemon=True).start()
    
    def draw_hint_arrow(self, from_pos, to_pos):
        """ヒント矢印を描画（黄色）"""
        self.clear_hint_arrow()
        
        sr, sc = from_pos
        er, ec = to_pos
        
        # 矢印の開始点と終了点（マスの中心）
        x1 = sc * CELL_SIZE + CELL_SIZE // 2
        y1 = sr * CELL_SIZE + CELL_SIZE // 2 + self.top_offset
        x2 = ec * CELL_SIZE + CELL_SIZE // 2
        y2 = er * CELL_SIZE + CELL_SIZE // 2 + self.top_offset
        
        # 矢印を描画
        self.hint_arrow_id = self.canvas.create_line(
            x1, y1, x2, y2,
            arrow=tk.LAST,
            fill="blue",
            width=4,
            tags="hint_arrow"
        )
    
    def clear_hint_arrow(self):
        """ヒント矢印を削除"""
        if self.hint_arrow_id:
            self.canvas.delete(self.hint_arrow_id)
            self.hint_arrow_id = None
        self.canvas.delete("hint_arrow")
    
    def parse_usi_move(self, usi_move):
        """USI形式の指し手を解析（例: 7g7f -> ((6,6), (5,6))）"""
        if len(usi_move) < 4:
            return None, None
        
        # 持ち駒打ちの場合（例: P*5e）
        if '*' in usi_move:
            return None, None  # 持ち駒打ちは矢印表示しない
        
        from_str = usi_move[0:2]
        to_str = usi_move[2:4]
        
        try:
            # USI形式: 1a-9i (列=1-9, 行=a-i)
            from_col = 9 - int(from_str[0])
            from_row = ord(from_str[1]) - ord('a')
            to_col = 9 - int(to_str[0])
            to_row = ord(to_str[1]) - ord('a')
            return (from_row, from_col), (to_row, to_col)
        except Exception as e:
            print(f"Failed to parse USI move {usi_move}: {e}")
            return None, None

    def load_pieces(self):
        for piece, (col, row) in PIECE_COL_MAP.items():
            piece_img = self.sprite.crop((
                col * self.sprite_width, row * self.sprite_height,
                (col + 1) * self.sprite_width, (row + 1) * self.sprite_height
            ))
            piece_img = piece_img.resize((CELL_SIZE, CELL_SIZE))
            key_char = piece[1] if piece.startswith('+') else piece[0]
            side = "先手" if key_char.isupper() else "後手"
            self.piece_images[(piece, side)] = ImageTk.PhotoImage(piece_img)

    def draw_pieces(self):
        self.canvas.delete("piece")
        self.canvas.delete("kiki")
        self.canvas.delete("select")
        self.canvas.delete("captured_select")
        self.canvas.delete("drop_hint")
        self.clear_hint_arrow()  # ヒント矢印も削除
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                piece = self.board[r][c]
                if piece:
                    self.place_piece(piece, r, c)
        self.draw_captured_pieces()
        # キーパッドカーソルがあれば再描画
        try:
            self.draw_keypad_cursor()
        except Exception:
            pass

    def place_piece(self, piece, r, c):
        key_char = piece[1] if piece.startswith('+') else piece[0]
        side = "先手" if key_char.isupper() else "後手"
        x = c * CELL_SIZE + CELL_SIZE // 2
        y = r * CELL_SIZE + CELL_SIZE // 2 + self.top_offset  # 盤面のオフセット
        img = self.piece_images.get((piece, side))
        if img:
            self.piece_ids[r][c] = self.canvas.create_image(x, y, image=img, tags="piece")

    def draw_captured_pieces(self):
        """持ち駒を駒台に描画"""
        self.canvas.delete("captured")
        # 先手の駒台（下）
        for i, piece in enumerate(self.captured_by_sente):
            img = self.piece_images.get((piece, "先手"))
            if img:
                x = i * CELL_SIZE + CELL_SIZE // 2
                y = self.bottom_komadai_y0 + KOMADAI_HEIGHT // 2
                self.canvas.create_image(x, y, image=img, tags="captured")
        # 後手の駒台（上）
        for i, piece in enumerate(self.captured_by_gote):
            img = self.piece_images.get((piece, "後手"))
            if img:
                x = i * CELL_SIZE + CELL_SIZE // 2
                y = KOMADAI_HEIGHT // 2
                self.canvas.create_image(x, y, image=img, tags="captured")

    def highlight_kiki(self, kiki_list):
        self.canvas.delete("kiki")
        for (r, c) in kiki_list:
            x0 = c * CELL_SIZE
            y0 = r * CELL_SIZE + self.top_offset
            x1 = (c + 1) * CELL_SIZE
            y1 = (r + 1) * CELL_SIZE + self.top_offset
            # 青枠ではなく薄い赤の塗りつぶし（stippleで50%相当）
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                fill="#ff0000", outline="", stipple="gray50", tags="kiki"
            )

    def is_my_piece(self, piece):
        """駒が現在の手番の駒かどうかを判定"""
        if not piece:
            return False
        # 成り駒の場合は基本の駒文字を取得
        base_char = piece[1] if piece.startswith('+') else piece[0]
        # 大文字=先手の駒、小文字=後手の駒
        is_sente_piece = base_char.isupper()
        if self.turn == "先手":
            return is_sente_piece
        else:
            return not is_sente_piece

    def on_click(self, event):
        # 成り選択中/ゲーム終了時は他のクリックを無視
        if self.pending_move is not None or getattr(self, 'game_over', False):
            return
        # AI思考中は入力不可
        if getattr(self, 'ai_thinking', False):
            return
        # レビュー中（過去局面）なら指せない
        if self.is_review_mode():
            return
        c = event.x // CELL_SIZE
        r = (event.y - self.top_offset) // CELL_SIZE
        
        # 持ち駒台のクリック判定
        if event.y < KOMADAI_HEIGHT:  # 上側の駒台（後手）
            if self.turn == "後手":
                idx = event.x // CELL_SIZE
                if 0 <= idx < len(self.captured_by_gote):
                    self.select_captured_piece(idx, "後手")
            return
        # 下側の駒台（先手）領域内のみ有効
        elif self.bottom_komadai_y0 <= event.y < self.bottom_komadai_y0 + KOMADAI_HEIGHT:
            if self.turn == "先手":
                idx = event.x // CELL_SIZE
                if 0 <= idx < len(self.captured_by_sente):
                    self.select_captured_piece(idx, "先手")
            return
        # パネル領域はクリック無視
        elif event.y >= self.panel_y0:
            return
        
        # 盤面のクリック判定
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            return

        # 持ち駒を選択している場合
        if self.selected_captured is not None:
            # 空いているマスにのみ打てる
            if not self.board[r][c]:
                self.drop_piece(r, c)
            else:
                # 選択を解除
                self.canvas.delete("captured_select")
                self.selected_captured = None
            return

        # 盤面の駒を選択する場合
        if self.selected is None:
            if self.board[r][c]:
                piece = self.board[r][c]
                # 自分の手番の駒のみ選択可能
                if not self.is_my_piece(piece):
                    return
                # 打ち候補ハイライトは消す
                self.canvas.delete("drop_hint")
                self.selected = (r, c)
                self.canvas.create_rectangle(
                    c * CELL_SIZE, r * CELL_SIZE + 100, (c + 1) * CELL_SIZE, (r + 1) * CELL_SIZE + 100,
                    outline="red", width=3, tags="select"
                )
                # 合法手のみをハイライト（自玉が詰まない手）
                self.kiki_list = self.get_legal_moves_for_piece(piece, r, c)
                self.highlight_kiki(self.kiki_list)
        else:
            sr, sc = self.selected
            # ハイライトされた箇所（利き）にのみ移動可能
            if (r, c) in self.kiki_list:
                self.canvas.delete("select")
                self.canvas.delete("kiki")
                self.move_piece(sr, sc, r, c)
                self.kiki_list = []
            else:
                # ハイライトされていない箇所をクリックした場合、選択を解除
                self.canvas.delete("select")
                self.canvas.delete("kiki")
                self.kiki_list = []
            self.selected = None

    def select_captured_piece(self, idx, side):
        """持ち駒を選択"""
        self.canvas.delete("captured_select")
        self.canvas.delete("select")
        self.canvas.delete("kiki")
        self.canvas.delete("drop_hint")
        # 同じ持ち駒を2回押したら解除
        if self.selected_captured is not None and self.selected_captured[1] == idx and self.selected_captured[2] == side:
            self.selected_captured = None
            return
        self.selected = None
        self.kiki_list = []
        
        if side == "先手":
            piece = self.captured_by_sente[idx]
            y = self.bottom_komadai_y0 + KOMADAI_HEIGHT // 2
        else:
            piece = self.captured_by_gote[idx]
            y = KOMADAI_HEIGHT // 2
        
        x = idx * CELL_SIZE + CELL_SIZE // 2
        self.selected_captured = (piece, idx, side)
        
        # 持ち駒を赤枠で囲む
        self.canvas.create_rectangle(
            idx * CELL_SIZE, y - CELL_SIZE // 2,
            (idx + 1) * CELL_SIZE, y + CELL_SIZE // 2,
            outline="red", width=3, tags="captured_select"
        )
        # 打てるマスをハイライト
        legal = self.get_legal_drop_squares(piece, side)
        self.highlight_drop_targets(legal)

    def drop_piece(self, r, c):
        """持ち駒を盤面に打つ"""
        if self.selected_captured is None:
            return
        
        piece, idx, side = self.selected_captured
        # 合法打ちか（自玉に王手がかからない）を先に確認
        nb_check = self.simulate_drop(self.board, side, piece, r, c)
        if nb_check is None or self.is_in_check(side, nb_check):
            return
        # 二歩チェック（同じ筋に自分の未成の歩があるか）
        if (piece == 'P' and side == '先手') or (piece == 'p' and side == '後手'):
            if self.has_unpromoted_pawn_in_file(side, c, self.board):
                print('二歩のため打てません')
                return
        # 打ち歩詰めチェック（歩打ちで相手が即詰みになるのは反則）
        if (piece == 'P' and side == '先手') or (piece == 'p' and side == '後手'):
            if not self.board[r][c]:
                nb = [row[:] for row in self.board]
                nb[r][c] = piece
                opponent = '後手' if side == '先手' else '先手'
                if self.is_in_check(opponent, nb) and not self.has_any_legal_move(opponent, nb):
                    print('打ち歩詰めのため打てません')
                    return
        
        # 持ち駒リストから削除
        if side == "先手":
            self.captured_by_sente.pop(idx)
        else:
            self.captured_by_gote.pop(idx)
        
        # 盤面に配置
        self.board[r][c] = piece
        self.selected_captured = None
        self.canvas.delete("captured_select")
        self.canvas.delete("drop_hint")
        self.draw_pieces()
        self.turn = "後手" if self.turn == "先手" else "先手"
        self.check_and_maybe_show_result()
        self.save_history()
        self.schedule_ai_move_if_needed()

    def get_legal_drop_squares(self, piece, side):
        """持ち駒を打てる場所のリストを返す"""
        legal = []
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                # 空いているマスのみ
                if not self.board[r][c]:
                    # 二歩チェック
                    if (piece == 'P' and side == '先手') or (piece == 'p' and side == '後手'):
                        if self.has_unpromoted_pawn_in_file(side, c, self.board):
                            continue
                    # 打ち歩詰めチェック
                    if (piece == 'P' and side == '先手') or (piece == 'p' and side == '後手'):
                        nb = [row[:] for row in self.board]
                        nb[r][c] = piece
                        opponent = '後手' if side == '先手' else '先手'
                        if self.is_in_check(opponent, nb) and not self.has_any_legal_move(opponent, nb):
                            continue
                    # 自玉に王手がかからないかチェック
                    nb = self.simulate_drop(self.board, side, piece, r, c)
                    if nb is not None and not self.is_in_check(side, nb):
                        legal.append((r, c))
        return legal

    def highlight_drop_targets(self, cells):
        """持ち駒を打てる場所をハイライト"""
        self.canvas.delete("drop_hint")
        for (r, c) in cells:
            x0 = c * CELL_SIZE
            y0 = r * CELL_SIZE + self.top_offset
            x1 = (c + 1) * CELL_SIZE
            y1 = (r + 1) * CELL_SIZE + self.top_offset
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                fill="#ff0000", outline="", stipple="gray50", tags="drop_hint"
            )

    # --- Keypad cursor helpers ---
    def draw_keypad_cursor(self):
        """盤上の現在のキーパッドカーソル位置を表示する（黄色の枠）"""
        try:
            self.canvas.delete("keypad_cursor")
            r, c = self.kp_r, self.kp_c
            x0 = c * CELL_SIZE
            y0 = r * CELL_SIZE + self.top_offset
            x1 = (c + 1) * CELL_SIZE
            y1 = (r + 1) * CELL_SIZE + self.top_offset
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="yellow", width=3, tags="keypad_cursor")
        except Exception:
            pass

    def move_keypad_cursor(self, dr, dc):
        """カーソルを移動（dr,dcは行列の増分）"""
        nr = max(0, min(BOARD_SIZE - 1, self.kp_r + dr))
        nc = max(0, min(BOARD_SIZE - 1, self.kp_c + dc))
        self.kp_r, self.kp_c = nr, nc
        # 表示更新
        self.draw_keypad_cursor()

    def keypad_confirm(self):
        """キーパッドの決定キー（5）が押されたときの処理: 現在カーソル位置をクリックしたのと同じ扱いにする"""
        # create a fake event with coordinates at center of the cell
        class _E: pass
        e = _E()
        e.x = self.kp_c * CELL_SIZE + CELL_SIZE // 2
        e.y = self.kp_r * CELL_SIZE + CELL_SIZE // 2 + self.top_offset
        self.on_click(e)

    def move_piece(self, sr, sc, r, c):
        piece = self.board[sr][sc]
        target = self.board[r][c]

        # 取る処理
        if target:
            if self.turn == "先手":
                captured = self.to_sente_piece(target)
                self.captured_by_sente.append(captured)
            else:
                captured = self.to_gote_piece(target)
                self.captured_by_gote.append(captured)

        # 成り判定と選択UI
        base_piece = piece.replace("+", "")
        side = self.turn
        if self.can_promote(piece, sr, r, side) and not piece.startswith("+"):
            if self.must_promote(piece, sr, r, side):
                piece = "+" + base_piece
            else:
                # 盤面への配置は保留し、UIで選択させる
                self.pending_move = (sr, sc, r, c, base_piece, side)
                self.show_promotion_ui(r, c, base_piece, side)
                return

        # 合法手チェック（自玉に王手がかからないか）
        will_promote = piece.startswith('+')
        nb_check = self.simulate_move(self.board, sr, sc, r, c, promote=will_promote)
        if self.is_in_check(side, nb_check):
            return

        # 駒を移動
        self.board[r][c] = piece
        self.board[sr][sc] = ""

        # 描画更新
        self.draw_pieces()

        # 手番交代
        self.turn = "後手" if self.turn == "先手" else "先手"
        print("現在のSFEN:", self.board_to_sfen())
        # 詰み判定
        self.check_and_maybe_show_result()
        # 局面保存
        self.save_history()
        # AI手番なら思考
        self.schedule_ai_move_if_needed()

    # --- 成り選択UI ---
    def show_promotion_ui(self, r: int, c: int, base_piece: str, side: str):
        """成/不成の選択UIを盤上に表示"""
        self.clear_promotion_ui()
        # パネル位置計算
        panel_w = CELL_SIZE * 2 + 16
        panel_h = CELL_SIZE + 28
        x0 = c * CELL_SIZE
        y0 = r * CELL_SIZE + self.top_offset
        # 右端/下端ははみ出さないように調整
        max_w = BOARD_SIZE * CELL_SIZE
        max_h = self.top_offset + BOARD_SIZE * CELL_SIZE
        if x0 + panel_w > max_w:
            x0 = max_w - panel_w
        if y0 + panel_h > max_h:
            y0 = max_h - panel_h
        # 背景
        bg = self.canvas.create_rectangle(x0, y0, x0 + panel_w, y0 + panel_h, fill="#fff8dc", outline="#c99", width=2, tags=("promotion_ui",))
        self.promotion_widget_ids.append(bg)
        # 不成の画像
        normal_key = (base_piece, side)
        promote_key = ("+" + base_piece, side)
        img_normal = self.piece_images.get(normal_key)
        img_promote = self.piece_images.get(promote_key)
        # 画像参照保持
        self._promotion_imgs["normal"] = img_normal
        self._promotion_imgs["promote"] = img_promote
        # 配置座標
        nx = x0 + 8 + CELL_SIZE // 2
        px = x0 + 8 + CELL_SIZE + 8 + CELL_SIZE // 2
        cy = y0 + 8 + CELL_SIZE // 2
        # 不成
        nid = self.canvas.create_image(nx, cy, image=img_normal, tags=("promotion_ui", "promotion_no"))
        self.promotion_widget_ids.append(nid)
        nlabel = self.canvas.create_text(nx, y0 + panel_h - 10, text="不成", font=("Arial", 12), tags=("promotion_ui", "promotion_no"))
        self.promotion_widget_ids.append(nlabel)
        # 成
        pid = self.canvas.create_image(px, cy, image=img_promote, tags=("promotion_ui", "promotion_yes"))
        self.promotion_widget_ids.append(pid)
        plabel = self.canvas.create_text(px, y0 + panel_h - 10, text="成", font=("Arial", 12), tags=("promotion_ui", "promotion_yes"))
        self.promotion_widget_ids.append(plabel)
        # クリックハンドラ
        self.canvas.tag_bind("promotion_no", "<Button-1>", lambda e: self.choose_promotion(False))
        self.canvas.tag_bind("promotion_yes", "<Button-1>", lambda e: self.choose_promotion(True))

    def clear_promotion_ui(self):
        for _id in getattr(self, "promotion_widget_ids", []):
            try:
                self.canvas.delete(_id)
            except Exception:
                pass
        self.promotion_widget_ids = []
        # 画像参照は残しておいても問題ないが、開放したい場合は以下を有効化
        # self._promotion_imgs.clear()

    def choose_promotion(self, do_promote: bool):
        if not self.pending_move:
            return
        sr, sc, r, c, base_piece, side = self.pending_move
        # 強制成りは上書き
        if self.must_promote(base_piece, sr, r, side):
            do_promote = True
        piece = "+" + base_piece if do_promote else base_piece
        # 合法性チェック（自玉に王手にならない）
        nb_check = self.simulate_move(self.board, sr, sc, r, c, promote=do_promote)
        if self.is_in_check(side, nb_check):
            # 不合法な選択（例: 不成だと自王手）
            return
        # 駒を移動
        self.board[r][c] = piece
        self.board[sr][sc] = ""
        # UIクリア
        self.clear_promotion_ui()
        self.pending_move = None
        # 描画更新と手番交代
        self.draw_pieces()
        self.turn = "後手" if self.turn == "先手" else "先手"
        print("現在のSFEN:", self.board_to_sfen())
        # 詰み判定
        self.check_and_maybe_show_result()
        # 局面保存
        self.save_history()
        # AI手番なら思考
        self.schedule_ai_move_if_needed()

    def to_sente_piece(self, piece):
        """後手の駒を先手用の持ち駒に変換"""
        base = piece.replace('+', '')
        return base.upper()

    def to_gote_piece(self, piece):
        """先手の駒を後手用の持ち駒に変換"""
        base = piece.replace('+', '')
        return base.lower()

    def has_unpromoted_pawn_in_file(self, side: str, col: int, board) -> bool:
        target = 'P' if side == '先手' else 'p'
        for rr in range(BOARD_SIZE):
            if board[rr][col] == target:
                return True
        return False

    # --- 所有者判定 ---
    def belongs_to_side(self, piece: str, side: str) -> bool:
        if not piece:
            return False
        base_char = piece[1] if piece.startswith('+') else piece[0]
        is_sente = base_char.isupper()
        return (side == '先手' and is_sente) or (side == '後手' and not is_sente)

    # --- 成り判定ヘルパー ---
    def is_promotable(self, piece: str) -> bool:
        """この駒種が成り対象か（+が付いていない歩香桂銀角飛のみ）"""
        if not piece:
            return False
        if piece.startswith('+'):
            return False
        base = piece[0]
        return base in {'P', 'L', 'N', 'S', 'B', 'R', 'p', 'l', 'n', 's', 'b', 'r'}

    def in_promotion_zone(self, row: int, side: str) -> bool:
        """rowが成りゾーンにあるか判定。先手は上段(0-2)、後手は下段(6-8)。"""
        if side == '先手':
            return row in (0, 1, 2)
        else:
            return row in (6, 7, 8)

    def must_promote(self, piece: str, sr: int, r: int, side: str) -> bool:
        """成りが強制かどうか（先手の香/桂/歩が最奥で動けなくなる手や、後手も同様）。
        簡易実装: 桂は最奥/手前2段目、香と歩は最奥段に進むと強制成り。
        """
        if not self.is_promotable(piece):
            return False
        base = piece[0]
        if side == '先手':
            # 先手: 0段目が最奥、1段目が手前2段
            if base in {'P', 'L'} and r == 0:
                return True
            if base == 'N' and r <= 1:
                return True
        else:
            # 後手: 8段目が最奥、7段目が手前2段
            if base in {'p', 'l'} and r == 8:
                return True
            if base == 'n' and r >= 7:
                return True
        return False

    def can_promote(self, piece: str, sr: int, r: int, side: str) -> bool:
        """移動前後どちらかが成りゾーンで、成り対象駒なら成れる"""
        if not self.is_promotable(piece):
            return False
        return self.in_promotion_zone(sr, side) or self.in_promotion_zone(r, side)

    # --- 盤面ユーティリティ ---
    def board_to_sfen_rows_from(self, board):
        rows = []
        for r in range(BOARD_SIZE):
            empty = 0
            row_sfen = ""
            for c in range(BOARD_SIZE):
                p = board[r][c]
                if not p:
                    empty += 1
                else:
                    if empty > 0:
                        row_sfen += str(empty)
                        empty = 0
                    row_sfen += p
            if empty > 0:
                row_sfen += str(empty)
            rows.append(row_sfen)
        return rows

    def find_king(self, side: str, board):
        target = 'K' if side == '先手' else 'k'
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if board[r][c] == target:
                    return (r, c)
        return None

    def get_all_attacked_squares(self, attacker_side: str, board):
        attacked = set()
        rows = self.board_to_sfen_rows_from(board)
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                p = board[r][c]
                if p and self.belongs_to_side(p, attacker_side):
                    try:
                        lst = get_koma_kiki_sfen(p, (r, c), rows)
                        for pos in lst:
                            attacked.add(tuple(pos))
                    except Exception:
                        # 念のため安全側に無視
                        pass
        return attacked

    def is_in_check(self, side: str, board) -> bool:
        kpos = self.find_king(side, board)
        if not kpos:
            # 王が見つからない＝負け扱い
            return True
        opponent = '後手' if side == '先手' else '先手'
        attacked = self.get_all_attacked_squares(opponent, board)
        return kpos in attacked

    def simulate_move(self, board, sr, sc, r, c, promote: bool):
        nb = [row[:] for row in board]
        piece = nb[sr][sc]
        # 捕獲は持ち駒には加算しない（合法手探索のみ）
        base = piece.replace('+', '')
        if promote and not piece.startswith('+') and self.is_promotable(piece):
            piece = '+' + base
        nb[r][c] = piece
        nb[sr][sc] = ""
        return nb

    def simulate_drop(self, board, side: str, piece: str, r: int, c: int):
        nb = [row[:] for row in board]
        if nb[r][c]:
            return None
        # 最奥段制約（簡易）
        if side == '先手':
            if piece in {'P', 'L'} and r == 0:
                return None
            if piece == 'N' and r <= 1:
                return None
        else:
            if piece in {'p', 'l'} and r == 8:
                return None
            if piece == 'n' and r >= 7:
                return None
        # 二歩（未成）禁止
        if (piece == 'P' and side == '先手') or (piece == 'p' and side == '後手'):
            if self.has_unpromoted_pawn_in_file(side, c, nb):
                return None
        nb[r][c] = piece
        # 打ち歩詰め禁止
        if (piece == 'P' and side == '先手') or (piece == 'p' and side == '後手'):
            opponent = '後手' if side == '先手' else '先手'
            if self.is_in_check(opponent, nb) and not self.has_any_legal_move(opponent, nb):
                return None
        return nb

    def has_any_legal_move(self, side: str, board) -> bool:
        rows = self.board_to_sfen_rows_from(board)
        # 盤上の移動
        for sr in range(BOARD_SIZE):
            for sc in range(BOARD_SIZE):
                p = board[sr][sc]
                if not p or not self.belongs_to_side(p, side):
                    continue
                try:
                    moves = get_koma_kiki_sfen(p, (sr, sc), rows)
                except Exception:
                    moves = []
                for (r, c) in moves:
                    # 成りなし
                    nb = self.simulate_move(board, sr, sc, r, c, promote=False)
                    if not self.is_in_check(side, nb):
                        return True
                    # 成りあり
                    if self.can_promote(p, sr, r, side):
                        nbp = self.simulate_move(board, sr, sc, r, c, promote=True)
                        if not self.is_in_check(side, nbp):
                            return True
        # 打ち
        captured = self.captured_by_sente if side == '先手' else self.captured_by_gote
        for piece in captured:
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if board[r][c]:
                        continue
                    nb = self.simulate_drop(board, side, piece, r, c)
                    if nb is None:
                        continue
                    if not self.is_in_check(side, nb):
                        return True
        return False

    def check_and_maybe_show_result(self):
        if getattr(self, 'game_over', False):
            return
        side = self.turn  # 今から指す側
        if self.is_in_check(side, self.board) and not self.has_any_legal_move(side, self.board):
            winner = '後手' if side == '先手' else '先手'
            self.show_result(winner)

    def show_result(self, winner: str, resign: bool = False):
        self.game_over = True
        # オーバーレイ
        overlay = self.canvas.create_rectangle(0, 0, BOARD_SIZE*CELL_SIZE, self.total_height, fill="#000000", stipple="gray25", outline="")
        self.result_widget_ids.append(overlay)
        msg = f"{winner}の勝ち（詰み）" if not resign else f"{winner}の勝ち（降参）"
        tid = self.canvas.create_text(BOARD_SIZE*CELL_SIZE//2, (self.total_height)//2 - 40, text=msg, fill="#ffffff", font=("Meiryo", 28, "bold"))
        self.result_widget_ids.append(tid)
        # ボタン: ホームへ戻る / 感想戦
        btn_opts = dict(font=("Meiryo", 12), width=14)
        y = (self.total_height)//2 + 20
        btn_home = tk.Button(self.root, text="ホームへ戻る", command=self.go_home, **btn_opts)
        btn_review = tk.Button(self.root, text="感想戦", command=self.enter_review_mode, **btn_opts)
        self.result_widget_ids.append(self.canvas.create_window(BOARD_SIZE*CELL_SIZE//2 - 90, y, window=btn_home))
        self.result_widget_ids.append(self.canvas.create_window(BOARD_SIZE*CELL_SIZE//2 + 90, y, window=btn_review))
        # キー操作
        self.root.bind('<Escape>', lambda e: self.close_result())
        self.root.bind('r', lambda e: self.reset_game())

    def enter_review_mode(self):
        # 感想戦（レビュー）モードへ: 局面履歴の最終手に移動し、レビュー操作のみ有効
        self.close_result()
        self.go_last()

    # --- AI連携 ---
    def schedule_ai_move_if_needed(self):
        if not getattr(self, 'ai_enabled', False):
            return
        if getattr(self, 'game_over', False) or self.is_review_mode():
            return
        if self.turn != getattr(self, 'ai_side', '後手'):
            return
        if getattr(self, 'pending_move', None) is not None:
            return
        if getattr(self, 'ai_thinking', False):
            return
        # 思考開始
        self.ai_thinking = True
        self.show_ai_status('AI思考中…')
        # 現局面のSFEN
        sfen = self.board_to_sfen()
        print(f"DEBUG: Sending SFEN to AI: {sfen}")
        byoyomi = getattr(self, 'ai_byoyomi_ms', 2000)
        threading.Thread(target=self._ai_thread_worker, args=(sfen, byoyomi), daemon=True).start()

    def show_ai_status(self, text=None):
        # 下部パネル左側に簡易ステータス
        try:
            if self.ai_status_id is not None:
                self.canvas.delete(self.ai_status_id)
                self.ai_status_id = None
            if text:
                self.ai_status_id = self.canvas.create_text(10, self.panel_y0 + PANEL_HEIGHT//2 -30, anchor=tk.W, text=text, fill="#333", font=("Meiryo", 11))
        except Exception:
            pass

    def _ai_thread_worker(self, sfen: str, byoyomi: int):
        try:
            # USI position形式に変換: "sfen {board} {turn} {hand} {move_count}"
            position_str = f"sfen {sfen}"
            params = {
                'byoyomi': str(byoyomi),
                'position': position_str,
            }
            print(f"DEBUG: API request params: {params}")
            url = AI_ENDPOINT + '?' + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = resp.read()
                text = data.decode('utf-8', errors='ignore')
        except Exception as e:
            text = f"ERROR: {e}"
        # UIスレッドに戻す
        self.root.after(0, lambda: self._on_ai_response(text))

    def _on_ai_response(self, text: str):
        move = self.parse_bestmove_response(text)
        print(f"DEBUG: Received AI response. Parsed bestmove: '{move}'")
        print(f"DEBUG: Full response text: {text[:500]}")  # 最初の500文字
        if move is None:
            self.show_ai_status('AI通信エラー')
            self.ai_thinking = False
            return
        # AI手の適用
        applied = self.apply_ai_move(move)
        # リセットステータス
        self.ai_thinking = False
        self.show_ai_status(None)
        if not applied:
            # 念のため
            self.show_ai_status('AI指し手不正')

    def parse_bestmove_response(self, text: str):
        # 1) JSON形式を試す
        try:
            obj = json.loads(text)
            # "bestmove"キーを探す
            if isinstance(obj, dict) and 'bestmove' in obj:
                bm = obj['bestmove']
                if isinstance(bm, str) and bm.strip():
                    return bm.strip()
        except Exception:
            pass
        # 2) USIの"bestmove <move>"を抽出（フォールバック）
        m = re.search(r"bestmove\s+([\w\*\+]+)", text)
        if m:
            return m.group(1)
        return None

    def usi_square_to_rc(self, sq: str):
        # USI標準: 筋(file)=1-9（右から左：1筋が左端、9筋が右端）、段(rank)=a-i（上から下）
        # 盤面配列: row 0=最上段(a), col 0=9筋（右端）
        # 例: "7g" → 筋7, 段g → col=9-7=2, row=6
        # 例: "1a" → 筋1, 段a → col=9-1=8, row=0
        if len(sq) != 2:
            raise ValueError(f"Invalid USI square: {sq}")
        file_char = sq[0]  # '1'-'9'
        rank_char = sq[1]  # 'a'-'i'
        if not (file_char.isdigit() and 'a' <= rank_char <= 'i'):
            raise ValueError(f"Invalid USI square format: {sq}")
        file_num = int(file_char)  # 1-9
        col = 9 - file_num         # 1筋→8, 9筋→0
        row = ord(rank_char) - ord('a')  # a→0 .. i→8
        return (row, col)

    def apply_ai_move(self, move: str) -> bool:
        move = move.strip()
        if move in ('resign',):
            # 人間の勝ち
            winner = '先手' if self.ai_side == '後手' else '後手'
            self.show_result(winner)
            return True
        # ドロップ: P*7f
        if '*' in move:
            try:
                parts = move.split('*')
                if len(parts) != 2:
                    print(f"AI drop parse error: {move}")
                    return False
                pch = parts[0].strip()
                to_sq = parts[1].strip()
                r, c = self.usi_square_to_rc(to_sq)
                # 駒種を手番に合わせて変換
                piece = pch.upper() if self.ai_side == '先手' else pch.lower()
                # 駒台から1枚削除できるか
                cap_list = self.captured_by_sente if self.ai_side == '先手' else self.captured_by_gote
                if piece not in cap_list:
                    print(f"AI drop: piece {piece} not in hand")
                    return False
                if self.board[r][c]:
                    print(f"AI drop: target square ({r},{c}) occupied")
                    return False
                cap_list.remove(piece)
                self.board[r][c] = piece
                # 描画等
                self.draw_pieces()
                self.turn = '後手' if self.turn == '先手' else '先手'
                print(f"AI dropped {piece} at ({r},{c})")
                self.check_and_maybe_show_result()
                self.save_history()
                return True
            except Exception as e:
                print(f"AI drop exception: {e}")
                return False
        # 通常手: 7g7f or 7g7f+
        try:
            promote = move.endswith('+')
            core = move[:-1] if promote else move
            if len(core) < 4:
                print(f"AI move too short: {move}")
                return False
            from_sq = core[:2]
            to_sq = core[2:4]
            print(f"DEBUG: Parsing move '{move}' -> from={from_sq}, to={to_sq}")
            sr, sc = self.usi_square_to_rc(from_sq)
            r, c = self.usi_square_to_rc(to_sq)
            print(f"DEBUG: Converted to: from=({sr},{sc}), to=({r},{c})")
            piece = self.board[sr][sc]
            print(f"DEBUG: AI {self.ai_side} trying to move '{piece}' from ({sr},{sc}) to ({r},{c})")
            print(f"DEBUG: Board state at ({sr},{sc}): '{self.board[sr][sc]}'")
            if not piece:
                print(f"AI move: source ({sr},{sc}) empty")
                return False
            if not self.belongs_to_side(piece, self.ai_side):
                print(f"AI move: piece '{piece}' does not belong to {self.ai_side}")
                print(f"DEBUG: belongs_to_side check failed. Current turn={self.turn}, ai_side={self.ai_side}")
                # 盤面の一部を表示
                print(f"DEBUG: Board rows 0-2 (gote):")
                for rr in range(3):
                    print(f"  row {rr}: {self.board[rr]}")
                print(f"DEBUG: Board rows 6-8 (sente):")
                for rr in range(6, 9):
                    print(f"  row {rr}: {self.board[rr]}")
                return False
            target = self.board[r][c]
            # 取る処理
            if target:
                if self.ai_side == '先手':
                    captured = self.to_sente_piece(target)
                    self.captured_by_sente.append(captured)
                else:
                    captured = self.to_gote_piece(target)
                    self.captured_by_gote.append(captured)
            # 成り適用
            base_piece = piece.replace('+', '')
            if promote:
                piece = '+' + base_piece
            else:
                # 強制成りは自動
                if self.must_promote(piece, sr, r, self.ai_side) and not piece.startswith('+'):
                    piece = '+' + base_piece
            # 移動
            self.board[r][c] = piece
            self.board[sr][sc] = ''
            # 描画/手番交代/判定
            self.draw_pieces()
            self.turn = '後手' if self.turn == '先手' else '先手'
            print(f"AI moved from ({sr},{sc}) to ({r},{c}), promote={promote}")
            self.check_and_maybe_show_result()
            self.save_history()
            return True
        except Exception as e:
            print(f"AI move exception: {e}")
            return False

    def close_result(self):
        for _id in getattr(self, 'result_widget_ids', []):
            try:
                self.canvas.delete(_id)
            except Exception:
                pass
        self.result_widget_ids = []
        self.game_over = False
        # アンバインドは省略（上書きされるため影響軽微）

    def reset_game(self):
        # 盤面と状態を初期化
        self.board = sfen_to_board(initial_sfen)
        self.piece_ids = [[None]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.selected = None
        self.selected_captured = None
        self.turn = '先手'
        self.kiki_list = []
        self.pending_move = None
        self.promotion_widget_ids = []
        self._promotion_imgs = {}
        self.captured_by_sente = []
        self.captured_by_gote = []
        self.close_promotion_and_result()
        self.draw_pieces()
        # 履歴をリセットして初期局面を保存
        self.history = []
        self.history_index = -1
        self.save_history(truncate_future=False)

    # --- レビュー/履歴機能 ---
    def is_review_mode(self) -> bool:
        return 0 <= self.history_index < len(self.history)-1

    def snapshot_state(self):
        # 盤面・持ち駒・手番をディープコピー
        board_copy = [row[:] for row in self.board]
        sente_caps = self.captured_by_sente[:]
        gote_caps = self.captured_by_gote[:]
        return {
            'board': board_copy,
            'sente_caps': sente_caps,
            'gote_caps': gote_caps,
            'turn': self.turn,
        }

    def restore_state(self, state):
        self.board = [row[:] for row in state['board']]
        self.captured_by_sente = state['sente_caps'][:]
        self.captured_by_gote = state['gote_caps'][:]
        self.turn = state['turn']
        # 画面クリア
        self.canvas.delete("select")
        self.canvas.delete("kiki")
        self.canvas.delete("captured_select")
        self.canvas.delete("drop_hint")
        self.close_promotion_and_result()
        self.draw_pieces()

    def save_history(self, truncate_future: bool = True):
        # プロモ選択中は確定していないので保存しない
        if self.pending_move is not None:
            return
        if truncate_future and self.history_index < len(self.history)-1:
            # 途中から指した場合は未来の履歴を破棄
            self.history = self.history[:self.history_index+1]
        snap = self.snapshot_state()
        self.history.append(snap)
        self.history_index = len(self.history)-1

    def go_first(self):
        if not self.history:
            return
        self.history_index = 0
        self.restore_state(self.history[self.history_index])

    def go_last(self):
        if not self.history:
            return
        self.history_index = len(self.history)-1
        self.restore_state(self.history[self.history_index])

    def go_prev(self):
        if self.history_index > 0:
            self.history_index -= 1
            self.restore_state(self.history[self.history_index])

    def go_next(self):
        if self.history_index < len(self.history)-1:
            self.history_index += 1
            self.restore_state(self.history[self.history_index])

    def create_review_controls(self):
        # 下部パネルにレビューコントロールを中央揃えで横並び配置（上側）
        center_x = BOARD_SIZE * CELL_SIZE // 2
        y = self.panel_y0 + 40
        btn_opts = dict(font=("Meiryo", 12), width=4)
        self.btn_first = tk.Button(self.root, text="⏮", command=self.go_first, **btn_opts)
        self.btn_prev  = tk.Button(self.root, text="◀", command=self.go_prev, **btn_opts)
        self.btn_next  = tk.Button(self.root, text="▶", command=self.go_next, **btn_opts)
        self.btn_last  = tk.Button(self.root, text="⏭", command=self.go_last, **btn_opts)
        self.canvas.create_window(center_x - 90, y, window=self.btn_first)
        self.canvas.create_window(center_x - 30, y, window=self.btn_prev)
        self.canvas.create_window(center_x + 30, y, window=self.btn_next)
        self.canvas.create_window(center_x + 90, y, window=self.btn_last)

    # --- 合法手生成（自玉が王手にならない手） ---
    def get_legal_moves_for_piece(self, piece: str, sr: int, sc: int):
        side = self.turn
        rows = self.board_to_sfen_rows()
        try:
            moves = get_koma_kiki_sfen(piece, (sr, sc), rows)
        except Exception:
            moves = []
        legal = []
        for (r, c) in moves:
            # 成り有無の候補を列挙
            promote_flags = [False]
            if not piece.startswith('+') and self.can_promote(piece, sr, r, side):
                if self.must_promote(piece, sr, r, side):
                    promote_flags = [True]
                else:
                    promote_flags = [False, True]
            ok = False
            for pf in promote_flags:
                nb = self.simulate_move(self.board, sr, sc, r, c, promote=pf)
                if not self.is_in_check(side, nb):
                    ok = True
                    break
            if ok:
                legal.append((r, c))
        return legal

    def close_promotion_and_result(self):
        try:
            self.clear_promotion_ui()
        except Exception:
            pass
        try:
            self.close_result()
        except Exception:
            pass

    def board_to_sfen_rows(self):
        rows = []
        for r in range(BOARD_SIZE):
            empty = 0
            row_sfen = ""
            for c in range(BOARD_SIZE):
                p = self.board[r][c]
                if not p:
                    empty += 1
                else:
                    if empty > 0:
                        row_sfen += str(empty)
                        empty = 0
                    row_sfen += p
            if empty > 0:
                row_sfen += str(empty)
            rows.append(row_sfen)
        return rows

    def board_to_sfen(self):
        rows = self.board_to_sfen_rows()
        sfen_board = "/".join(rows)
        # 標準SFEN: b=先手, w=後手（次に指す側）
        turn_s = "b" if self.turn == "先手" else "w"
        # 持ち駒をSFEN形式で構築
        hand = ""
        # 先手の持ち駒（大文字で順序: RBGSNLP）
        piece_order_sente = ['R', 'B', 'G', 'S', 'N', 'L', 'P']
        for pc in piece_order_sente:
            cnt = self.captured_by_sente.count(pc)
            if cnt > 0:
                if cnt > 1:
                    hand += str(cnt)
                hand += pc
        # 後手の持ち駒（小文字で順序: rbgsnlp）
        piece_order_gote = ['r', 'b', 'g', 's', 'n', 'l', 'p']
        for pc in piece_order_gote:
            cnt = self.captured_by_gote.count(pc)
            if cnt > 0:
                if cnt > 1:
                    hand += str(cnt)
                hand += pc
        if not hand:
            hand = "-"
        return f"{sfen_board} {turn_s} {hand} 1"

if __name__ == "__main__":
    root = tk.Tk()
    app = ShogiApp(root)
    root.mainloop()