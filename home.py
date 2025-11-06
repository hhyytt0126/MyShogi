import os
import tkinter as tk
from tkinter import messagebox


class HomeApp:
	def __init__(self, root: tk.Tk):
		self.root = root
		self.root.title("将棋 ホーム")
		# ShogiApp と同じサイズ: width=9*64=576, height=上駒台100 + 盤576 + 下駒台100 + パネル100 = 876
		self.root.geometry("576x926")

		# スクリプトのあるディレクトリをカレントに（画像の相対パス対策）
		try:
			os.chdir(os.path.dirname(__file__))
		except Exception:
			pass

		self.frame = tk.Frame(self.root, bg="#f7f7f7")
		self.frame.pack(fill=tk.BOTH, expand=True)

		title = tk.Label(
			self.frame,
			text="将棋",
			font=("Meiryo", 36, "bold"),
			bg="#f7f7f7",
		)
		title.pack(pady=40)

		subtitle = tk.Label(
			self.frame,
			text="ホーム",
			font=("Meiryo", 16),
			bg="#f7f7f7",
		)
		subtitle.pack(pady=4)

		btn_style = {
			"font": ("Meiryo", 16, "bold"),
			"bg": "#4CAF50",
			"fg": "white",
			"activebackground": "#43a047",
			"activeforeground": "white",
			"relief": tk.FLAT,
			"padx": 20,
			"pady": 12,
			"width": 16,
		}

		start_btn = tk.Button(self.frame, text="対人戦を開始", command=self.start_game, **btn_style)
		start_btn.pack(pady=12)

		ai_btn = tk.Button(self.frame, text="AIと対戦を開始", command=self.start_game_vs_ai, **{**btn_style, "bg": "#8E24AA", "activebackground": "#7B1FA2"})
		ai_btn.pack(pady=8)

		rules_btn = tk.Button(self.frame, text="ルール(簡易)", command=self.show_rules, **{**btn_style, "bg": "#2196F3", "activebackground": "#1e88e5"})
		rules_btn.pack(pady=8)

		exit_btn = tk.Button(self.frame, text="終了", command=self._on_exit, **{**btn_style, "bg": "#e53935", "activebackground": "#d32f2f"})
		exit_btn.pack(pady=32)

		# menu button list for keypad navigation
		self.menu_buttons = [start_btn, ai_btn, rules_btn, exit_btn]
		# store original bg colors so we can restore when selection changes
		self._menu_bg = [b.cget("bg") for b in self.menu_buttons]
		self._menu_index = 0
		self._update_menu_selection()

		# try to register keypad callback (safe on non-RPi)
		try:
			import key_pad
			try:
				# Ensure no stale callbacks remain (prevent duplicate calls after UI switches)
				try:
					if hasattr(key_pad, "unregister_all"):
						key_pad.unregister_all()
				except Exception:
					pass
				key_pad.start_polling()
			except Exception:
				pass
			def _on_keypad_key(key):
				if not key:
					return
				if key == '5':
					# confirm
					self.menu_buttons[self._menu_index].invoke()
					return
				if key == '8':
					# up
					self._menu_index = (self._menu_index - 1) % len(self.menu_buttons)
					self._update_menu_selection()
					return
				if key == '2':
					# down
					self._menu_index = (self._menu_index + 1) % len(self.menu_buttons)
					self._update_menu_selection()
			try:
				key_pad.register_callback(_on_keypad_key)
				self._keypad_cb = _on_keypad_key
			except Exception:
				self._keypad_cb = None
		except Exception:
			self._keypad_cb = None


	def start_game(self):
		# 遅延インポートで循環依存や起動の重さを回避
		from shogi import ShogiApp

		# cleanup keypad registration before switching UI
		self._cleanup_keypad()
		# ホームUIを消してゲームを起動（同じTkルートを使う）
		self.frame.destroy()
		ShogiApp(self.root, ai_enabled=False)

	def start_game_vs_ai(self):
		from shogi import ShogiApp
		self._cleanup_keypad()
		self.frame.destroy()
		# 先手=人間, 後手=AI (byoyomi 2000ms)
		ShogiApp(self.root, ai_enabled=True, ai_side='後手', ai_byoyomi_ms=2000)

	def show_rules(self):
		message = (
			"基本ルール:\n"
			"- 自分の駒だけを選択して動かせます\n"
			"- 成り: 成りゾーン移動で成/不成を選択\n"
			"- 持ち駒: 駒台から選んで合法手のマスが赤でハイライト\n"
			"- 禁止: 二歩, 打ち歩詰め\n"
			"- 終局: 詰み判定で結果表示\n"
		)
		messagebox.showinfo("ルール(簡易)", message)

	def _update_menu_selection(self):
		# Visualize selection by changing relief and focus
		for i, btn in enumerate(self.menu_buttons):
			if i == self._menu_index:
				btn.config(relief=tk.SUNKEN)
				try:
					btn.focus_set()
				except Exception:
					pass
			else:
				btn.config(relief=tk.FLAT)

	def _cleanup_keypad(self):
		# Unregister keypad callback and stop polling if available
		try:
			import key_pad
			if getattr(self, "_keypad_cb", None):
				try:
					key_pad.unregister_callback(self._keypad_cb)
				except Exception:
					pass
				# clear stored reference
				self._keypad_cb = None
			try:
				key_pad.stop_polling()
			except Exception:
				pass
			# best-effort: clear any leftover callbacks to avoid duplicates on re-entry
			try:
				if hasattr(key_pad, "unregister_all"):
					key_pad.unregister_all()
			except Exception:
				pass
		except Exception:
			pass

	def _on_exit(self):
		self._cleanup_keypad()
		self.root.destroy()


if __name__ == "__main__":
	root = tk.Tk()
	app = HomeApp(root)
	root.mainloop()

