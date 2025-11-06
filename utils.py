def get_single_set_bit(value):
    """
    上位4ビット・下位4ビットのそれぞれで
    1ビットだけ立っている場合、そのビット番号を返す。
    立っていない場合や複数ビットが立っている場合は None を返す。
    
    戻り値:
        (upper_bit_index, lower_bit_index)
    """
    upper4 = (value >> 4) & 0x0F  # 上位4ビット
    lower4 = value & 0x0F         # 下位4ビット

    # 上位4ビットの処理
    upper_bits = [3-i for i in range(4) if (upper4 >> (3-i)) & 1]
    upper_bit_index = upper_bits[0] if len(upper_bits) == 1 else None

    # 下位4ビットの処理
    lower_bits = [3-i for i in range(4) if (lower4 >> (3-i)) & 1]
    lower_bit_index = lower_bits[0] if len(lower_bits) == 1 else None

    return lower_bit_index, upper_bit_index
