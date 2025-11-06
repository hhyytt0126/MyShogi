def sfen_to_board(sfen_rows):
    """
    SFEN盤面文字列のリスト (例: ['lnsgkgsnl', '1r5b1', ...]) を
    9x9の盤面リストのリストに変換する。
    """
    board = []
    for row in sfen_rows:
        board_row = []
        i = 0
        while i < len(row):
            if row[i].isdigit():
                # 数字は空きマス
                board_row.extend([''] * int(row[i]))
                i += 1
            elif row[i] == '+':
                # '+' は成駒
                if i + 1 < len(row):
                    board_row.append('+' + row[i+1])
                    i += 2
                else:
                    # SFEN形式として不正な場合への対策
                    board_row.append('+') 
                    i += 1
            else:
                # 駒
                board_row.append(row[i])
                i += 1
        board.append(board_row)
    return board

def get_koma_kiki_sfen(koma_name, koma_pos, sfen_rows):
    """
    SFEN盤面で指定された駒の移動可能マスを返す（全駒対応）。
    味方の駒は飛び越えられない、相手の駒は取れるが飛び越えられない、というルールを適用。
    """
    # 盤面を生成
    board = sfen_to_board(sfen_rows)

    r, c = koma_pos  # 駒の位置 (行, 列)
    koma_kiki = []
    is_upper = koma_name.isupper()  # 先手かどうか (大文字)
    forward = -1 if is_upper else 1  # 先手は上向き (-1)、後手は下向き (+1)
    
    # 駒の所有者と相手の駒の判定ロジック
    def is_opponent(target_koma):
        if target_koma == '':
            return False
        # 先手(大文字)は後手(小文字)を、後手(小文字)は先手(大文字)を取れる
        return (is_upper and target_koma.islower()) or (not is_upper and target_koma.isupper())
    
    # 移動可能判定関数 (主に1マス移動の駒用、または大駒の1マス追加移動用)
    def can_move(nr, nc):
        if 0 <= nr < 9 and 0 <= nc < 9:
            target = board[nr][nc]
            if target == '':
                return True # 空きマス
            if is_opponent(target):
                return True # 相手の駒
            # 味方の駒がいる場合は移動不可
            return False
        return False

    koma_base = koma_name.upper()

    # --- 1マス移動の駒 ---

    # 王 (K)
    if koma_base == 'K':
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r + dr, c + dc
                if can_move(nr, nc):
                    koma_kiki.append((nr, nc))

    # 金 (G) と成駒 (成銀+S, 成桂+N, 成香+L, と金+P)
    elif koma_base in ['G', '+S', '+N', '+L', '+P']:
        # 縦、横、前斜め (5方向) + 真後ろ (1方向) = 6方向
        moves = [(forward, 0), (0, -1), (0, 1), (forward, -1), (forward, 1), (-forward, 0)]
        
        for dr, dc in moves:
            nr, nc = r + dr, c + dc
            if can_move(nr, nc):
                koma_kiki.append((nr, nc))

    # 銀 (S)
    elif koma_base == 'S':
        # 前方3マス (縦1、斜め2) と斜め後ろ2マス
        moves = [(forward, 0), (forward, -1), (forward, 1), (-forward, -1), (-forward, 1)]
        for dr, dc in moves:
            nr, nc = r + dr, c + dc
            if can_move(nr, nc):
                koma_kiki.append((nr, nc))

    # 桂 (N)
    elif koma_base == 'N':
        # 2マス前、1マス左右 (桂馬は飛び越せる唯一の駒)
        for dc in [-1, 1]:
            nr, nc = r + 2 * forward, c + dc
            if can_move(nr, nc):
                koma_kiki.append((nr, nc))

    # 歩 (P)
    elif koma_base == 'P':
        nr = r + forward
        if 0 <= nr < 9 and can_move(nr, c):
            koma_kiki.append((nr, c))
            
    # --- 長距離移動の駒 (利きが遮断されるルール適用) ---
    
    # 香 (L)
    elif koma_base == 'L':
        dr, dc = forward, 0 # 前方にのみ進む
        nr = r + dr
        while 0 <= nr < 9:
            target_koma = board[nr][c]
            if target_koma == '':
                koma_kiki.append((nr, c))
            elif is_opponent(target_koma):
                koma_kiki.append((nr, c))
                break # 相手の駒を取ったらそこで利きは中断
            else: # 味方の駒
                break # 味方の駒に当たったら利きは中断 (移動も不可)
            nr += dr # さらに前に進む

    # 飛車 (R) と 竜 (+R)
    elif koma_base in ['R', '+R']:
        # 飛車: 縦横の利き (遮断ルール適用)
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 9 and 0 <= nc < 9:
                target_koma = board[nr][nc]
                if target_koma == '':
                    koma_kiki.append((nr, nc))
                elif is_opponent(target_koma):
                    koma_kiki.append((nr, nc))
                    break # 相手の駒を取ったらそこで利きは中断
                else: # 味方の駒
                    break # 味方の駒に当たったら利きは中断 (移動も不可)
                nr += dr
                nc += dc
        
        # 竜 (+R) の追加の動き: 斜め1マス
        if koma_base == '+R':
            for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nr, nc = r + dr, c + dc
                if can_move(nr, nc): # 1マス移動なので can_move で判定
                    koma_kiki.append((nr, nc))


    # 角 (B) と 馬 (+B)
    elif koma_base in ['B', '+B']:
        # 角: 斜めの利き (遮断ルール適用)
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 9 and 0 <= nc < 9:
                target_koma = board[nr][nc]
                if target_koma == '':
                    koma_kiki.append((nr, nc))
                elif is_opponent(target_koma):
                    koma_kiki.append((nr, nc))
                    break # 相手の駒を取ったらそこで利きは中断
                else: # 味方の駒
                    break # 味方の駒に当たったら利きは中断 (移動も不可)
                nr += dr
                nc += dc
        
        # 馬 (+B) の追加の動き: 縦横1マス
        if koma_base == '+B':
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if can_move(nr, nc): # 1マス移動なので can_move で判定
                    koma_kiki.append((nr, nc))

    return koma_kiki
