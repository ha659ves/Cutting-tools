import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import re
import csv
import os
import io


# ===== 你可以自己设置这里 =====
SMALL_WIDTH = 700       # 小窗口宽度
LARGE_WIDTH = 1000      # 大窗口宽度
WINDOW_HEIGHT = 840     # 窗口高度


LINE_PREFIX = '"...'        # 每行加的前缀
LINE_SUFFIX = '..."'        # 每行加的后缀
PACK_TARGET_LEN = 85       # 每行尽量接近这个长度
SOFT_COMMA_TOTAL_LEN = 75  # 句子超过这个长度，才考虑把逗号作为候选断点
SOFT_COMMA_MIN_LEFT = 40   # 逗号前面至少这么长，才允许作为候选小段
SOFT_COMMA_MIN_RIGHT = 25  # 逗号后面至少这么长，才允许作为候选小段
MIN_LINE_LEN = 70       # 短于这个长度，会尽量合并下一句
VERY_SHORT_LEN = 35     # 很短的句子，会合并到前一句
MAX_LINE_LEN = 120      # 超过这个长度，就尝试按逗号断开
TARGET_SPLIT_LEN = 105  # 断逗号时，尽量让上一行接近这个长度
LONG_SPLIT_LEN = 150    # 祷告排比句不超过这个长度时尽量保留
PACK_TARGET_LEN = 95   # 每行尽量接近这个长度

JOIN_SPACE = ""         # 合并句子时中间是否加空格；想自然一点改成 " "
CONVERT_TO_LOWERCASE = True   # True = 全部转小写，False = 保留原大小写


CSV_INPUT_COLUMN = 0    # A列，0代表A列
CSV_OUTPUT_COLUMN = 1   # B列，1代表B列
CSV_HAS_HEADER = False  # 如果CSV第一行是标题，就改成 True

# ===== 新增：识别 Google Sheet 红黑字脚本生成的【1】【2】【3】标记 =====
# 支持：
# 【1】正文
# 【 1 】正文
# [1] 正文
# 1| 正文
# 1｜正文
# 作用：断行后把标记放到 "...正文..." 前面，例如：
# 【2】"...can i pray for your son or daughter..."
MARK_TOKEN_RE = re.compile(r'(?:【\s*([123])\s*】|\[\s*([123])\s*\]|([123])\s*[|｜])')
# =============================


is_large_window = False

# 保存批量处理后的结果，用于一键复制回 Google Sheet
batch_results = []
batch_originals = []

# 搜索状态
search_matches = []
search_current_index = -1

# 非相邻小段合并状态：这里保存被加入合并列表的小段序号
merge_pick_indices = []




def remove_all_emoji(text):
    """删除大部分 emoji、图标、特殊表情符号。数字 emoji 会先转英文，所以不会误删 1️⃣/2️⃣。"""

    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002700-\U000027BF"
        "\U00002600-\U000026FF"
        "\U00002300-\U000023FF"
        "\U00002B00-\U00002BFF"
        "\U0000200D"
        "\U0000FE0F"
        "\U000020E3"
        "]+",
        flags=re.UNICODE
    )

    text = emoji_pattern.sub(" ", text)
    text = re.sub(r"[\U0001F3FB-\U0001F3FF]", " ", text)
    return text


def get_int_from_entry(entry_name, default_value, min_value=1):
    """安全读取输入框中的整数。输入框还没创建时，直接返回默认值。"""

    try:
        entry = globals().get(entry_name)
        value = int(entry.get().strip())
        if value < min_value:
            return default_value
        return value
    except:
        return default_value


def apply_length_settings(show_message=False):
    """
    从界面输入框读取断行字符设置。
    目标字符：每段尽量接近这个长度。
    最大字符：超过这个长度时，优先按 . ! ?，其次按逗号，最后才按空格兜底。
    """

    global PACK_TARGET_LEN, MAX_LINE_LEN, TARGET_SPLIT_LEN
    global SOFT_COMMA_TOTAL_LEN, SOFT_COMMA_MIN_LEFT, SOFT_COMMA_MIN_RIGHT

    target_len = get_int_from_entry("target_len_entry", PACK_TARGET_LEN, 20)
    max_len = get_int_from_entry("max_len_entry", MAX_LINE_LEN, 40)

    # 最大长度不能小于目标长度，否则会很容易碎
    if max_len < target_len:
        max_len = target_len + 20

    PACK_TARGET_LEN = target_len
    MAX_LINE_LEN = max_len

    # 逗号断点也跟着用户设置走
    TARGET_SPLIT_LEN = max(30, int((target_len + max_len) / 2))
    SOFT_COMMA_TOTAL_LEN = max(40, int(target_len * 0.85))
    SOFT_COMMA_MIN_LEFT = max(20, int(target_len * 0.45))
    SOFT_COMMA_MIN_RIGHT = max(18, int(target_len * 0.30))

    if show_message:
        root.title(f"英文段落智能断行工具 - 已应用：目标 {PACK_TARGET_LEN} / 最大 {MAX_LINE_LEN}")

    return True

def clean_text(text):
    """清理文本：去换行、去双引号、去冒号、序号转英文"""

    if text is None:
        return ""

    text = str(text).strip()

    # 大写转小写
    if CONVERT_TO_LOWERCASE:
        text = text.lower()

    # 去掉首尾双引号
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]

    # 换行变空格
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")



    # 数字 emoji 转英文
    number_emoji_map = {
        "1️⃣": "one ",
        "2️⃣": "two ",
        "3️⃣": "three ",
        "4️⃣": "four ",
        "5️⃣": "five ",
        "6️⃣": "six ",
        "7️⃣": "seven ",
        "8️⃣": "eight ",
        "9️⃣": "nine ",
    }

    for k, v in number_emoji_map.items():
        text = text.replace(k, v)

    # 普通数字编号转英文
    # 支持：
    # 1 prayer   -> one prayer
    # 2 prayer   -> two prayer
    # 3 prayer   -> three prayer
    # 3.prayer   -> three prayer
    # 3. prayer  -> three prayer
    # 3) prayer  -> three prayer
    # 3、prayer  -> three prayer
    # 3: prayer  -> three prayer
    # 3-prayer   -> three prayer
    # 也支持 10-99，比如 12 prayer -> twelve prayer
    number_word_map = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
        19: "nineteen",
        20: "twenty",
        30: "thirty",
        40: "forty",
        50: "fifty",
        60: "sixty",
        70: "seventy",
        80: "eighty",
        90: "ninety",
    }

    def number_to_words(num_text):
        try:
            n = int(num_text)
        except:
            return num_text

        if n in number_word_map:
            return number_word_map[n]

        if 21 <= n <= 99:
            tens = (n // 10) * 10
            ones = n % 10

            if ones == 0:
                return number_word_map.get(tens, num_text)

            return number_word_map.get(tens, str(tens)) + " " + number_word_map.get(ones, str(ones))

        return num_text

    def replace_number(match):
        num = match.group(1)
        return number_to_words(num) + " "

    # 处理“小段前面的数字编号”。
    # 数字前面必须是开头、空格、引号或常见分隔符；
    # 数字后面必须最终接英文，避免把 Luke 17 26 这种经文数字乱改。
    # 这样 1/2/3/4... 都会处理，不会只处理 2。
    text = re.sub(
        r'(?:(?<=^)|(?<=[\s"“”\'\(\[\{,;]))([1-9]\d?)(?:[\.\)、:：\-])?\s*(?=[a-zA-Z])',
        replace_number,
        text
    )

    # 去掉双引号，包括弯引号和普通双引号
    text = text.replace("“", "")
    text = text.replace("”", "")
    text = text.replace('"', "")

    # 去掉冒号。用空格替换，避免 Luke 17:26 变成 Luke 1726
    text = re.sub(r'\s*[:：]\s*', ' ', text)

    # 删除所有 emoji / 图标 / 特殊表情
    text = remove_all_emoji(text)

    # 常见错别拆分修正
    text = text.replace("fr ee", "free")

    # 连续空格压缩成一个
    text = " ".join(text.split())

    return text


def split_into_sentences(text):
    """按 . ! ? 拆成完整句子，保留句尾标点"""

    sentences = re.findall(r'[^.!?]+[.!?]|[^.!?]+$', text)

    result = []
    for s in sentences:
        s = s.strip()
        if s:
            result.append(s)

    return result


def is_numbered_sentence(sentence):
    """判断是不是 one / two / three / four 开头的编号句"""

    lower = sentence.lower().strip()

    return lower.startswith((
        "one ",
        "two ",
        "three ",
        "four ",
        "five ",
        "six ",
        "seven ",
        "eight ",
        "nine "
    ))


def is_prayer_parallel(sentence):
    """判断是不是 may..., may..., and may... 这种祷告排比句"""

    lower = sentence.lower()
    may_count = lower.count("may ")

    return may_count >= 2


def split_by_space_if_too_long(line):
    """最后兜底：没有合适逗号时，按最接近目标长度的空格断开"""

    line = line.strip()

    if len(line) <= MAX_LINE_LEN:
        return [line]

    space_positions = [m.start() for m in re.finditer(" ", line)]

    if not space_positions:
        return [line]

    best_pos = None
    best_score = 999999

    for pos in space_positions:
        first = line[:pos].strip()
        second = line[pos:].strip()

        first_len = len(first)
        second_len = len(second)

        if first_len < MIN_LINE_LEN:
            continue

        if second_len < 25:
            continue

        # 不判断 for / to / of 这些词，只看长度接近目标值
        score = abs(first_len - TARGET_SPLIT_LEN)

        if score < best_score:
            best_score = score
            best_pos = pos

    if best_pos is None:
        return [line]

    first = line[:best_pos].strip()
    second = line[best_pos:].strip()

    result = [first]

    if len(second) > MAX_LINE_LEN:
        result.extend(split_by_space_if_too_long(second))
    else:
        result.append(second)

    return result


def split_line_if_too_long(line):
    """
    如果合并后的整行太长，就断开。
    优先级：
    1. 优先按逗号断。
    2. 没有合适逗号，才按空格兜底。
    不再按 for/to/of/and/but/so 等词判断。
    """

    line = line.strip()

    if len(line) <= MAX_LINE_LEN:
        return [line]

    # may..., may..., and may... 这种祷告排比句，长度不太夸张时保留完整
    if is_prayer_parallel(line) and len(line) <= LONG_SPLIT_LEN:
        return [line]

    comma_positions = [m.start() for m in re.finditer(",", line)]

    # 没有逗号，直接按空格兜底
    if not comma_positions:
        return split_by_space_if_too_long(line)

    best_pos = None
    best_score = 999999

    for pos in comma_positions:
        first_len = pos + 1
        second_len = len(line) - first_len

        if first_len < MIN_LINE_LEN:
            continue

        if second_len < 25:
            continue

        # 只按长度选最合适的逗号
        score = abs(first_len - TARGET_SPLIT_LEN)

        if score < best_score:
            best_score = score
            best_pos = pos

    # 有逗号，但没有合适逗号，也按空格兜底
    if best_pos is None:
        return split_by_space_if_too_long(line)

    first = line[:best_pos + 1].strip()
    second = line[best_pos + 1:].strip()

    result = [first]

    if len(second) > MAX_LINE_LEN:
        result.extend(split_line_if_too_long(second))
    else:
        result.append(second)

    return result


def should_not_merge_with_next(current, next_sentence):
    """判断当前句是否不应该和下一句合并"""

    c = current.strip().lower()
    n = next_sentence.strip().lower()

    # May 开头的完整祷告句，后面如果是 If 条件句，不合并
    if c.startswith("may ") and len(current) >= 45 and n.startswith("if "):
        return True

    # 后一句是新的祷告开头，不和前一句合并
    prayer_starters = (
        "dear god",
        "god,",
        "lord,",
        "may the lord",
        "may god",
        "father god",
        "heavenly father"
    )

    if len(current) >= 45 and n.startswith(prayer_starters):
        return True

    return False


def join_text(a, b):
    """合并两段文字：逗号后面加空格，其他按 JOIN_SPACE"""
    a = a.rstrip()
    b = b.lstrip()

    if not a:
        return b

    if not b:
        return a

    if a.endswith(","):
        return a + " " + b

    return a + JOIN_SPACE + b


def join_text(a, b):
    """合并两段文字：逗号后面自动加空格，其他按 JOIN_SPACE"""
    a = a.rstrip()
    b = b.lstrip()

    if not a:
        return b

    if not b:
        return a

    # 逗号后面保留一个空格
    if a.endswith(","):
        return a + " " + b

    return a + JOIN_SPACE + b


def split_sentence_by_soft_commas(sentence):
    """
    把逗号变成候选小段。
    注意：不是每个逗号都断，只选择前后长度都合适的逗号。
    """

    sentence = sentence.strip()

    if len(sentence) < SOFT_COMMA_TOTAL_LEN:
        return [sentence]

    if "," not in sentence:
        return [sentence]

    parts = []
    start = 0

    comma_positions = [m.start() for m in re.finditer(",", sentence)]

    for pos in comma_positions:
        left = sentence[start:pos + 1].strip()
        right = sentence[pos + 1:].strip()

        # 左边太短不切，右边太短也不切
        if len(left) >= SOFT_COMMA_MIN_LEFT and len(right) >= SOFT_COMMA_MIN_RIGHT:
            parts.append(left)
            start = pos + 1

    tail = sentence[start:].strip()

    if tail:
        parts.append(tail)

    if not parts:
        return [sentence]

    return parts


def make_atoms(sentences):
    """
    先把句子变成小段。
    句号是硬切分点。
    逗号是软切分点，用来辅助整体长度分配。
    """

    atoms = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        # 先按合适的逗号切成候选小段
        comma_parts = split_sentence_by_soft_commas(sentence)

        for part in comma_parts:
            part = part.strip()

            if not part:
                continue

            # 如果某个小段仍然太长，再用原来的长句拆分逻辑
            if len(part) > MAX_LINE_LEN:
                split_parts = split_line_if_too_long(part)

                for p in split_parts:
                    p = p.strip()
                    if p:
                        atoms.append(p)
            else:
                atoms.append(part)

    return atoms


def pack_atoms_by_length(atoms):
    """
    根据整体长度自动分行。
    核心：不看 May / If / Dear God，只看整体长度是否舒服。
    """

    n = len(atoms)

    if n == 0:
        return []

    dp = [float("inf")] * (n + 1)
    path = [-1] * (n + 1)

    dp[n] = 0

    for i in range(n - 1, -1, -1):
        current = ""

        for j in range(i, n):
            if current:
                candidate = join_text(current, atoms[j])
            else:
                candidate = atoms[j]

            length = len(candidate)

            # 超过最大长度，就不要继续合并
            if length > MAX_LINE_LEN and j > i:
                break

            # 越接近目标长度越好
            score = abs(length - PACK_TARGET_LEN) ** 2

            # 非最后一行太短，增加惩罚，避免碎行
            if j < n - 1 and length < MIN_LINE_LEN:
                score += 1500

            total_score = score + dp[j + 1]

            if total_score < dp[i]:
                dp[i] = total_score
                path[i] = j + 1

            current = candidate

    lines = []
    i = 0

    while i < n:
        next_i = path[i]

        if next_i == -1:
            lines.append(atoms[i])
            i += 1
            continue

        line = ""

        for k in range(i, next_i):
            if line:
                line = join_text(line, atoms[k])
            else:
                line = atoms[k]

        lines.append(line)
        i = next_i

    return lines


def build_lines(sentences):
    """
    新版核心算法：
    句号先拆句。
    逗号作为候选小段。
    最后根据整体长度重新组合。
    """

    atoms = make_atoms(sentences)
    lines = pack_atoms_by_length(atoms)

    return lines


def merge_short_lines_after_split(lines):
    """把逗号拆分后产生的短行，和后面的短句合并"""

    new_lines = []
    i = 0

    while i < len(lines):
        current = lines[i].strip()

        if not current:
            i += 1
            continue

        # 如果当前行很短，并且后面还有一行，就尝试合并后面
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()

            if (
                len(current) < 45
                and len(next_line) < 80
                and len(current) + len(next_line) <= MAX_LINE_LEN
            ):
                current = current + JOIN_SPACE + next_line
                i += 1

        new_lines.append(current)
        i += 1

    return new_lines


def is_amen_line(line):
    """判断是不是 Amen 这种短结尾"""

    l = line.strip().lower()

    return l in [
        "amen",
        "amen.",
        "amen!",
        "type amen",
        "type amen.",
        "type amen!"
    ]


def merge_short_lines_after_split(lines):
    """拆长句后，再处理 Amen 这种短尾巴，以及过短的碎行"""

    cleaned = []

    for line in lines:
        line = line.strip()
        if line:
            cleaned.append(line)

    # 第一轮：Amen / Type Amen 合并到上一行
    merged = []

    for line in cleaned:
        if merged and is_amen_line(line):
            merged[-1] = merged[-1] + JOIN_SPACE + line
        else:
            merged.append(line)

    # 第二轮：中间出现太短的碎行时，尝试和下一行合并
    final_lines = []
    i = 0

    while i < len(merged):
        current = merged[i].strip()

        if i + 1 < len(merged):
            next_line = merged[i + 1].strip()

            if (
                len(current) < 45
                and len(next_line) < 80
                and len(current) + len(next_line) <= MAX_LINE_LEN
                and not current.endswith(",")
            ):
                final_lines.append(current + JOIN_SPACE + next_line)
                i += 2
                continue

        final_lines.append(current)
        i += 1

    return final_lines



# =============================
# 新增：带【1】【2】【3】标记的文案处理
# 用来处理 Google Sheet 红黑字脚本生成的文本。
# 核心目标：
# 1. 【1】【2】【3】不进入正文。
# 2. 断行后，标记永远放在 "...正文..." 前面。
# 3. 同一个【1】段落被拆成多行时，每一行都保留【1】。
# =============================

def get_marker_from_match(match):
    """从 MARK_TOKEN_RE 的匹配里取出 1/2/3"""
    if not match:
        return None

    for group in match.groups():
        if group in ("1", "2", "3"):
            return group

    return None


def has_mode_marker_anywhere(text):
    """判断文本中是否包含【1】【2】【3】/[1]/1| 这类模式标记"""
    if text is None:
        return False

    return MARK_TOKEN_RE.search(str(text)) is not None


def normalize_raw_marked_text(text):
    """
    处理从 Google Sheet / 剪贴板过来的原始文本。
    有时单元格内容外面会带一层英文双引号，这里只去掉外层，不动正文。
    """
    if text is None:
        return ""

    text = str(text).strip()

    # Google Sheet 复制单个带换行的单元格时，外面可能包一层双引号
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]

    # CSV/TSV 里双引号可能会变成两个双引号
    text = text.replace('""', '"')

    return text.strip()


def split_marked_text_into_blocks(text):
    """
    把一条带标记的文案拆成块：
    【2】开场
    【1】祷告
    【2】结尾

    即使这些标记被 Google Sheet 复制成一整行，也能按标记拆开。
    """
    text = normalize_raw_marked_text(text)

    matches = list(MARK_TOKEN_RE.finditer(text))

    if not matches:
        return []

    blocks = []

    # 如果第一个标记前面有内容，也保留下来，但不加标记
    prefix = text[:matches[0].start()].strip()
    if prefix:
        blocks.append((None, prefix))

    for index, match in enumerate(matches):
        marker = get_marker_from_match(match)
        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(text)

        body = text[start:end].strip()

        # 清理 Google Sheet 单元格内部多余的引号
        body = body.strip()
        if len(body) >= 2 and body.startswith('"') and body.endswith('"'):
            body = body[1:-1].strip()

        if body:
            blocks.append((marker, body))

    return blocks


def clean_marked_body_before_process(body):
    """
    带标记的正文进入断行算法前，先去掉可能残留的外层包装。
    防止把已经处理过的【2】"...xxx..." 再处理时变成多余省略号。
    """
    body = str(body or "").strip()

    # 去掉外层英文双引号
    if len(body) >= 2 and body.startswith('"') and body.endswith('"'):
        body = body[1:-1].strip()

    # 如果正文已经是 ...xxx...，去掉外层省略号
    body = re.sub(r'^\s*\.+\s*', '', body)
    body = re.sub(r'\s*\.+\s*$', '', body)

    return body.strip()


def format_output_with_marker(lines, marker=None):
    """
    格式化断行结果。
    普通原逻辑：
    "...正文..."

    带标记新逻辑：
    【2】"...正文..."
    """
    formatted = []

    marker_prefix = ""
    if marker in ("1", "2", "3"):
        marker_prefix = f"【{marker}】"

    for line in lines:
        line = line.strip()

        if line:
            if line.endswith("."):
                line = line[:-1]

            formatted.append(marker_prefix + LINE_PREFIX + line + LINE_SUFFIX)

    return "\n\n".join(formatted)


def process_plain_text_without_marker(text):
    """原来的普通处理逻辑，不识别标记"""
    content = clean_text(text)

    if not content:
        return ""

    sentences = split_into_sentences(content)
    lines = build_lines(sentences)
    result = format_output(lines)

    return result


def process_marked_text(text):
    """
    新增：处理带【1】【2】【3】标记的文案。
    每个标记块单独断行，避免【2】开场和【1】祷告被合并到同一行。
    """
    blocks = split_marked_text_into_blocks(text)

    if not blocks:
        return process_plain_text_without_marker(text)

    output_parts = []

    for marker, body in blocks:
        body = clean_marked_body_before_process(body)
        content = clean_text(body)

        if not content:
            continue

        sentences = split_into_sentences(content)
        lines = build_lines(sentences)
        result = format_output_with_marker(lines, marker)

        if result:
            output_parts.append(result)

    return "\n\n".join(output_parts)



def format_output(lines):
    """每行前面和结尾都加...，避免句号后出现四个点"""

    formatted = []

    for line in lines:
        line = line.strip()
        if line:
            if line.endswith("."):
                line = line[:-1]
            formatted.append(LINE_PREFIX + line + LINE_SUFFIX)

    return "\n\n".join(formatted)


def process_one_text(text):
    """处理单条文案，返回最终断行结果"""

    # 每次处理前读取界面上的字符数设置
    apply_length_settings(show_message=False)

    # 新增：如果文本里已经有【1】【2】【3】标记，
    # 就按标记分块处理，并把标记放到 "...正文..." 前面。
    if has_mode_marker_anywhere(text):
        return process_marked_text(text)

    return process_plain_text_without_marker(text)


def paste_text():
    """普通粘贴：处理单条文案"""

    try:
        text = root.clipboard_get()
        text = clean_text(text)

        input_text.delete("1.0", tk.END)
        input_text.insert("1.0", text)

        split_sentences()

    except:
        messagebox.showwarning("提示", "剪贴板中没有文本内容")


def split_sentences():
    """处理输入框中的单条文案"""

    content = input_text.get("1.0", tk.END).strip()

    if not content:
        messagebox.showwarning("提示", "请输入内容")
        return

    result = process_one_text(content)

    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, result)


def parse_google_sheet_clipboard(text):
    """
    解析从 Google Sheet 复制出来的内容。
    支持单列、多行。
    如果复制了多列，只处理第一列。
    """

    rows = []

    try:
        reader = csv.reader(io.StringIO(text), delimiter="\t")
        for row in reader:
            rows.append(row)
    except:
        # 兜底：普通按行分割
        for line in text.splitlines():
            rows.append([line])

    texts = []

    for row in rows:
        if not row:
            texts.append("")
        else:
            texts.append(row[0])

    return texts


def paste_batch_from_sheet():
    """
    从 Google Sheet 复制多行后，点击这个按钮。
    自动把每一行当成一条文案处理。
    """

    global batch_results, batch_originals

    try:
        raw_text = root.clipboard_get()
    except:
        messagebox.showwarning("提示", "剪贴板中没有文本内容")
        return

    if not raw_text.strip():
        messagebox.showwarning("提示", "剪贴板中没有文本内容")
        return

    texts = parse_google_sheet_clipboard(raw_text)

    if not texts:
        messagebox.showwarning("提示", "没有解析到批量内容")
        return

    batch_originals = texts
    batch_results = []

    processed_count = 0

    for text in texts:
        if str(text).strip():
            result = process_one_text(text)
            processed_count += 1
        else:
            result = ""

        batch_results.append(result)

    # 输入框显示原始批量内容，方便检查
    input_text.delete("1.0", tk.END)
    input_text.insert("1.0", raw_text)

    # 输出框显示预览
    preview_parts = []

    for index, result in enumerate(batch_results, start=1):
        preview_parts.append(f"===== 第 {index} 条 =====")
        preview_parts.append(result if result else "[空]")

    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, "\n\n".join(preview_parts))

    # messagebox.showinfo(
    #     "完成",
    #     f"批量处理完成！\n\n读取行数：{len(texts)} 行\n有效处理：{processed_count} 行\n\n现在可以点击：复制批量结果"
    # )


def make_google_sheet_column_clipboard(values):
    """
    把批量结果做成 Google Sheet 可以识别的一列数据。
    每个结果是一个单元格。
    单元格内部的换行会尽量保留。
    """

    buffer = io.StringIO()

    writer = csv.writer(
        buffer,
        delimiter="\t",
        lineterminator="\n",
        quoting=csv.QUOTE_ALL
    )

    for value in values:
        writer.writerow([value])

    content = buffer.getvalue()

    # 只去掉最后一个换行，不影响单元格内部换行
    if content.endswith("\n"):
        content = content[:-1]

    return content


def copy_batch_results():
    """
    复制批量结果。
    回到 Google Sheet，点 B列起始单元格，直接 Ctrl+V。

    新增：复制前会先同步“批量预览”里的手动标记。
    这样你在输出框里给小段加的【1】【2】【3】，复制回 Google Sheet 时也会保留。
    """

    sync_batch_results_from_preview()

    if not batch_results:
        messagebox.showwarning("提示", "还没有批量结果，请先点击“粘贴批量并处理”")
        return

    content = make_google_sheet_column_clipboard(batch_results)

    root.clipboard_clear()
    root.clipboard_append(content)
    root.update()

    # messagebox.showinfo(
    #     "完成",
    #     f"已复制批量结果！\n\n共 {len(batch_results)} 行。\n现在回到 Google Sheet，点击 B列对应的第一格，然后 Ctrl+V。"
    # )


def read_csv_with_encoding(file_path):
    """尝试用不同编码读取CSV"""

    encodings = ["utf-8-sig", "utf-8", "gbk", "cp936"]

    last_error = None

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding, newline="") as f:
                sample = f.read(4096)
                f.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(sample)
                except:
                    dialect = csv.excel

                rows = list(csv.reader(f, dialect))

            return rows, encoding, dialect

        except Exception as e:
            last_error = e

    raise last_error


def batch_process_csv():
    """导入CSV，批量处理A列，把结果写入B列"""

    file_path = filedialog.askopenfilename(
        title="选择要处理的CSV文件",
        filetypes=[
            ("CSV 文件", "*.csv"),
            ("所有文件", "*.*")
        ]
    )

    if not file_path:
        return

    try:
        rows, encoding, dialect = read_csv_with_encoding(file_path)

        if not rows:
            messagebox.showwarning("提示", "CSV文件是空的")
            return

        processed_count = 0

        for row_index, row in enumerate(rows):
            # 如果第一行是标题，就跳过
            if CSV_HAS_HEADER and row_index == 0:
                while len(row) <= CSV_OUTPUT_COLUMN:
                    row.append("")

                if not row[CSV_OUTPUT_COLUMN].strip():
                    row[CSV_OUTPUT_COLUMN] = "处理结果"

                continue

            # 保证A列存在
            if len(row) <= CSV_INPUT_COLUMN:
                continue

            original_text = row[CSV_INPUT_COLUMN].strip()

            # 保证B列存在
            while len(row) <= CSV_OUTPUT_COLUMN:
                row.append("")

            if original_text:
                row[CSV_OUTPUT_COLUMN] = process_one_text(original_text)
                processed_count += 1
            else:
                row[CSV_OUTPUT_COLUMN] = ""

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        default_name = base_name + "_已处理.csv"

        save_path = filedialog.asksaveasfilename(
            title="保存处理后的CSV文件",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[
                ("CSV 文件", "*.csv"),
                ("所有文件", "*.*")
            ]
        )

        if not save_path:
            return

        # 用 utf-8-sig 保存，Excel 打开中文不容易乱码
        with open(save_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        # messagebox.showinfo(
        #     "完成",
        #     f"批量处理完成！\n\n处理数量：{processed_count} 行\n保存位置：\n{save_path}"
        # )

    except Exception as e:
        messagebox.showerror("错误", f"处理CSV失败：\n{e}")


def add_two_spaces():
    """给断行结果每一行前面加2个空格，避免重复添加"""

    content = output_text.get("1.0", tk.END).rstrip("\n")

    if not content.strip():
        messagebox.showwarning("提示", "没有可处理的断行结果")
        return

    lines = content.splitlines()
    new_lines = []

    for line in lines:
        if not line.strip():
            new_lines.append("")
        elif line.startswith("  "):
            new_lines.append(line)
        else:
            new_lines.append("  " + line)

    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, "\n".join(new_lines))


def copy_result():
    """复制单条结果到剪贴板，保留每行前面的空格"""

    content = output_text.get("1.0", tk.END)

    # 只去掉 Tkinter Text 自动多出来的最后一个换行，不删除开头空格
    content = content.rstrip("\n")

    if not content.strip():
        messagebox.showwarning("提示", "没有可复制的内容")
        return

    root.clipboard_clear()
    root.clipboard_append(content)
    root.update()


# =============================
# 小段模式标记工具
# 用法：鼠标点到输出框某一小段，点击【1】【2】【3】即可给这一小段加标记。
# 标记会放在小段最前面，例如：【1】"...lord, please..."
# 复制批量结果时，会自动同步这些标记到 batch_results。
# =============================

def is_preview_header_line(line):
    """判断是不是批量预览里的 ===== 第 X 条 ===== 标题行"""

    return re.match(r'^=+\s*第\s*\d+\s*条\s*=+\s*$', line.strip()) is not None


def remove_mode_marker_from_line(line):
    """清除一行开头已有的【1】【2】【3】/[1]/1| 标记，保留原来的缩进"""

    m = re.match(r'^(\s*)', line)
    leading = m.group(1) if m else ''
    rest = line[len(leading):]

    rest = re.sub(r'^(?:【[123]】|\[[123]\]|[123]\s*[|｜])\s*', '', rest).lstrip()

    return leading + rest


def add_mode_marker_to_line(line, mode):
    """给一行小段添加模式标记。mode 为 '1'/'2'/'3'，None 表示只清除标记"""

    clean_line = remove_mode_marker_from_line(line)

    if mode is None:
        return clean_line

    m = re.match(r'^(\s*)', clean_line)
    leading = m.group(1) if m else ''
    rest = clean_line[len(leading):]

    return leading + f'【{mode}】' + rest


def get_output_line_count():
    """获取输出框实际行数"""

    try:
        return int(output_text.index('end-1c').split('.')[0])
    except:
        return 1


def get_selected_line_numbers():
    """如果输出框中有选区，返回选中的行号列表；没有选区则返回空列表"""

    try:
        start = output_text.index(tk.SEL_FIRST)
        end = output_text.index(tk.SEL_LAST)
    except tk.TclError:
        return []

    start_line = int(start.split('.')[0])
    end_line = int(end.split('.')[0])

    return list(range(start_line, end_line + 1))


def find_nearest_target_line():
    """没有选区时，找到光标所在或附近最近的一条有效小段"""

    max_line = get_output_line_count()

    try:
        cur_line = int(output_text.index(tk.INSERT).split('.')[0])
    except:
        cur_line = max_line

    def is_valid_line(line_no):
        if line_no < 1 or line_no > max_line:
            return False

        line = output_text.get(f'{line_no}.0', f'{line_no}.end')

        if not line.strip():
            return False

        if line.strip() == '[空]':
            return False

        if is_preview_header_line(line):
            return False

        return True

    if is_valid_line(cur_line):
        return cur_line

    # 光标在空行时，优先找上方最近的小段；找不到再找下方
    for offset in range(1, 20):
        up = cur_line - offset
        down = cur_line + offset

        if is_valid_line(up):
            return up

        if is_valid_line(down):
            return down

    return None


def sync_batch_results_from_preview():
    """
    把输出框里的批量预览重新同步回 batch_results。
    这样手动加的【1】【2】【3】不会在“复制批量结果”时丢失。
    """

    global batch_results

    try:
        content = output_text.get('1.0', tk.END).rstrip('\n')
    except:
        return False

    lines = content.splitlines()

    blocks = []
    current_index = None
    current_lines = []
    has_preview_header = False

    for line in lines:
        m = re.match(r'^=+\s*第\s*(\d+)\s*条\s*=+\s*$', line.strip())

        if m:
            has_preview_header = True

            if current_index is not None:
                blocks.append((current_index, '\n'.join(current_lines).strip('\n')))

            current_index = int(m.group(1)) - 1
            current_lines = []
        else:
            if current_index is not None:
                current_lines.append(line)

    if current_index is not None:
        blocks.append((current_index, '\n'.join(current_lines).strip('\n')))

    if not has_preview_header:
        return False

    if not blocks:
        return False

    max_index = max(idx for idx, _ in blocks)
    new_results = [''] * (max(max_index + 1, len(batch_results)))

    for idx, value in blocks:
        if idx < 0:
            continue

        if value.strip() == '[空]':
            value = ''

        while len(new_results) <= idx:
            new_results.append('')

        new_results[idx] = value

    batch_results = new_results
    return True


def set_current_line_mode_marker(mode):
    """
    给当前小段添加/清除模式标记。
    mode: '1' 闭眼祷告，'2' 睁眼说话，'3' 闭眼流泪，None 清除标记。
    """

    selected_lines = get_selected_line_numbers()

    if selected_lines:
        target_lines = selected_lines
    else:
        line_no = find_nearest_target_line()
        target_lines = [line_no] if line_no else []

    changed = 0

    for line_no in target_lines:
        if not line_no:
            continue

        line = output_text.get(f'{line_no}.0', f'{line_no}.end')

        if not line.strip():
            continue

        if line.strip() == '[空]':
            continue

        if is_preview_header_line(line):
            continue

        new_line = add_mode_marker_to_line(line, mode)

        if new_line != line:
            output_text.delete(f'{line_no}.0', f'{line_no}.end')
            output_text.insert(f'{line_no}.0', new_line)
            changed += 1

    if changed <= 0:
        messagebox.showwarning('提示', '请先把鼠标点到要标记的小段里面，或者选中多个小段')
        return

    sync_batch_results_from_preview()

    if mode is None:
        root.title(f'英文段落智能断行工具 - 已清除 {changed} 个小段标记')
    else:
        root.title(f'英文段落智能断行工具 - 已给 {changed} 个小段添加【{mode}】标记')



# =============================
# 搜索 / 拆分 / 合并工具
# =============================

MODE_MARK_RE = re.compile(r'^\s*(?:【([123])】|\[([123])\]|([123])\s*[|｜])\s*')


def text_index_to_char_offset(index):
    """把 Text 控件索引转成从 1.0 开始的字符偏移"""
    try:
        return len(output_text.get('1.0', index))
    except:
        return 0


def char_offset_to_text_index(offset):
    """把字符偏移转成 Text 控件索引"""
    if offset < 0:
        offset = 0
    return f'1.0+{offset}c'


def get_editable_segments_from_content(content):
    """
    获取输出框里的小段块。
    小段以空行分隔，批量预览标题和 [空] 不算小段。
    """
    segments = []

    pattern = re.compile(r'(?s)(^|(?<=\n\n))(.+?)(?=\n\n|\Z)')

    for m in pattern.finditer(content):
        block = m.group(2)
        start = m.start(2)
        end = m.end(2)
        clean = block.strip()

        if not clean:
            continue

        if clean == '[空]':
            continue

        if is_preview_header_line(clean):
            continue

        segments.append({
            'start': start,
            'end': end,
            'text': block
        })

    return segments


def find_segment_by_offset(content, offset):
    """根据光标位置找到当前小段，光标在空行时找最近的小段"""
    segments = get_editable_segments_from_content(content)

    if not segments:
        return None

    for seg in segments:
        if seg['start'] <= offset <= seg['end']:
            return seg

    # 光标在空行时，找距离最近的小段
    nearest = None
    nearest_dist = 10 ** 9

    for seg in segments:
        if offset < seg['start']:
            dist = seg['start'] - offset
        elif offset > seg['end']:
            dist = offset - seg['end']
        else:
            dist = 0

        if dist < nearest_dist:
            nearest_dist = dist
            nearest = seg

    return nearest


def parse_segment_marker(segment_text):
    """读取小段开头的模式标记，返回 '1'/'2'/'3'/None"""
    m = MODE_MARK_RE.match(segment_text or '')

    if not m:
        return None

    for g in m.groups():
        if g:
            return g

    return None


def strip_segment_marker(segment_text):
    """去掉小段开头的模式标记"""
    return MODE_MARK_RE.sub('', segment_text or '', count=1).strip()


def parse_segment_parts(segment_text):
    """
    解析一个小段，返回：
    marker: 【1】【2】【3】标记
    inline_prefix: 例如 oh；如果是普通 "...正文..."，则为 None
    body: 不带外层引号、省略号和前缀的正文
    """
    raw = segment_text or ''
    marker = parse_segment_marker(raw)
    text = strip_segment_marker(raw).strip()

    # 去掉结尾外层后缀：..." 或 "
    if text.endswith(LINE_SUFFIX):
        text = text[:-len(LINE_SUFFIX)].strip()
    elif text.endswith('"'):
        text = text[:-1].strip()

    # 去掉开头第一个引号
    if text.startswith('"'):
        text = text[1:].strip()

    inline_prefix = None

    # 普通格式："...正文
    if text.startswith("..."):
        text = text[3:].strip()
    else:
        # 前缀格式："oh...正文
        m = re.match(r'^([a-zA-Z][a-zA-Z0-9_-]*)\.\.\.(.*)$', text, re.S)
        if m:
            inline_prefix = m.group(1)
            text = m.group(2).strip()

    # 兜底清理
    text = text.strip()
    text = re.sub(r'^\.+', '', text).strip()
    text = re.sub(r'\.+$', '', text).strip()

    return marker, inline_prefix, text


def unwrap_segment_body(segment_text):
    """
    去掉模式标记、外层 "...  ..."、以及 oh... 这类小段前缀，只保留正文。
    例如：【2】"oh...god is speaking..." -> god is speaking
    """
    marker, inline_prefix, body = parse_segment_parts(segment_text)
    return body


def normalize_body_for_wrap(body):
    """重新包小段前，清理正文，避免结尾出现四个点"""
    body = (body or '').strip()

    if body.endswith('.'):
        body = body[:-1].strip()

    return body


def wrap_segment_body_with_inline_prefix(body, marker=None, inline_prefix=None):
    """
    把正文重新包成小段格式。
    如果原小段有 oh... 这种前缀，拆分后两段都会继续使用 oh...
    """
    body = normalize_body_for_wrap(body)

    if not body:
        return ''

    marker_text = f'【{marker}】' if marker in ('1', '2', '3') else ''

    if inline_prefix:
        return marker_text + '"' + inline_prefix + '...' + body + LINE_SUFFIX

    return marker_text + LINE_PREFIX + body + LINE_SUFFIX


def wrap_segment_body(body, marker=None):
    """把正文重新包成小段格式，必要时加【1】【2】【3】"""
    return wrap_segment_body_with_inline_prefix(body, marker, None)


def join_bodies_with_comma(bodies):
    """合并多个小段正文，中间用英文逗号 + 空格，不用省略号"""
    cleaned = []

    for body in bodies:
        body = normalize_body_for_wrap(body)
        body = body.strip(' ,')
        if body:
            cleaned.append(body)

    if not cleaned:
        return ''

    result = cleaned[0]

    for body in cleaned[1:]:
        result = result.rstrip()

        if result.endswith(','):
            result = result + ' ' + body
        else:
            # 如果第一段以句号/问号/感叹号结尾，合并时去掉句尾符号，改成逗号连接
            result = result.rstrip('.!?')
            result = result.rstrip() + ', ' + body

    return result


def sync_after_output_edit():
    """输出框被标记/拆分/合并后，同步批量结果"""
    sync_batch_results_from_preview()


def get_segment_prefix_text():
    """读取小段前缀输入框。默认 oh。"""
    try:
        prefix = segment_prefix_entry.get().strip()
    except:
        prefix = 'oh'

    if not prefix:
        prefix = 'oh'

    return prefix


def add_or_remove_inline_prefix(segment_text, prefix, remove=False):
    """
    给一个小段添加/清除前缀。
    目标格式：
    原来：【2】"...god is speaking..."
    添加：【2】"oh...god is speaking..."
    注意：前缀加在第一个英文双引号后面，不加到【2】前面。
    """
    raw = segment_text or ''
    marker = parse_segment_marker(raw)
    marker_text = f'【{marker}】' if marker in ('1', '2', '3') else ''
    body = strip_segment_marker(raw).strip()

    prefix = (prefix or '').strip()

    if not prefix:
        return marker_text + body

    # 已经带了这个前缀
    wanted_start = '"' + prefix + '...'

    if remove:
        if body.startswith(wanted_start):
            body = '"...' + body[len(wanted_start):]
        return marker_text + body

    # 防重复
    if body.startswith(wanted_start):
        return marker_text + body

    # 标准断行格式："...正文..."
    if body.startswith('"...'):
        body = '"' + prefix + '...' + body[len('"...'):]
    elif body.startswith(LINE_PREFIX):
        body = '"' + prefix + '...' + body[len(LINE_PREFIX):]
    elif body.startswith('"'):
        body = '"' + prefix + body[1:]
    else:
        body = prefix + body

    return marker_text + body


def get_segments_by_selection_or_current(content, selected_only):
    """选中时处理选中的小段；没有选区时处理当前光标所在小段。"""
    segments = get_editable_segments_from_content(content)

    if not selected_only:
        return segments

    try:
        sel_start = text_index_to_char_offset(output_text.index(tk.SEL_FIRST))
        sel_end = text_index_to_char_offset(output_text.index(tk.SEL_LAST))
    except tk.TclError:
        cursor_offset = text_index_to_char_offset(tk.INSERT)
        seg = find_segment_by_offset(content, cursor_offset)
        return [seg] if seg else []

    selected = []

    for seg in segments:
        if seg['end'] > sel_start and seg['start'] < sel_end:
            selected.append(seg)

    return selected


def apply_inline_prefix_to_segments(selected_only=False, remove=False):
    """给全部小段或选中小段添加/清除前缀。"""
    content = output_text.get('1.0', 'end-1c')

    if not content.strip():
        messagebox.showwarning('提示', '没有可处理的断行结果')
        return

    prefix = get_segment_prefix_text()
    segments = get_segments_by_selection_or_current(content, selected_only)

    if not segments:
        messagebox.showwarning('提示', '没有找到可处理的小段')
        return

    changed = 0

    # 倒序替换，避免前面的替换影响后面的坐标
    for seg in reversed(segments):
        new_text = add_or_remove_inline_prefix(seg['text'], prefix, remove=remove)

        if new_text != seg['text']:
            output_text.delete(char_offset_to_text_index(seg['start']), char_offset_to_text_index(seg['end']))
            output_text.insert(char_offset_to_text_index(seg['start']), new_text)
            changed += 1

    sync_after_output_edit()

    if remove:
        root.title(f'英文段落智能断行工具 - 已清除 {changed} 个小段前缀')
    else:
        root.title(f'英文段落智能断行工具 - 已给 {changed} 个小段添加前缀：{prefix}')


def split_current_segment(second_mode=None):
    """
    从光标处拆分当前小段。
    第二段会自动继承上面的格式：
    1. 自动继承【1】【2】【3】标记。
    2. 自动继承 oh... 这类小段前缀。
    second_mode 为 '1'/'2'/'3' 时，第二段使用指定标记。
    """
    content = output_text.get('1.0', 'end-1c')

    if not content.strip():
        messagebox.showwarning('提示', '没有可拆分的内容')
        return

    cursor_offset = text_index_to_char_offset(tk.INSERT)
    seg = find_segment_by_offset(content, cursor_offset)

    if not seg:
        messagebox.showwarning('提示', '请把光标点到要拆分的小段里面')
        return

    marker, inline_prefix, body = parse_segment_parts(seg['text'])

    if len(body) < 2:
        messagebox.showwarning('提示', '当前小段太短，不能拆分')
        return

    local_offset = max(0, min(cursor_offset - seg['start'], len(seg['text'])))
    before_raw = seg['text'][:local_offset]
    before_body = unwrap_segment_body(before_raw)
    split_pos = len(before_body)

    # 防止点在最前或最后导致空段
    if split_pos <= 0 or split_pos >= len(body):
        messagebox.showwarning('提示', '请把光标点到小段正文中间位置再拆分')
        return

    left_body = body[:split_pos].strip(' ,')
    right_body = body[split_pos:].strip(' ,')

    if not left_body or not right_body:
        messagebox.showwarning('提示', '拆分位置不合适，左右有一边为空')
        return

    first_marker = marker
    second_marker = second_mode if second_mode in ('1', '2', '3') else marker

    first_text = wrap_segment_body_with_inline_prefix(left_body, first_marker, inline_prefix)
    second_text = wrap_segment_body_with_inline_prefix(right_body, second_marker, inline_prefix)
    replacement = first_text + '\n\n' + second_text

    output_text.delete(char_offset_to_text_index(seg['start']), char_offset_to_text_index(seg['end']))
    output_text.insert(char_offset_to_text_index(seg['start']), replacement)

    sync_after_output_edit()
    clear_merge_pick_segments()

    if second_marker:
        root.title(f'英文段落智能断行工具 - 已拆分，第二段标记为【{second_marker}】')
    else:
        root.title('英文段落智能断行工具 - 已从光标处拆分小段')


def merge_selected_segments():
    """
    合并选中的多个小段。
    合并时去掉每段外层的 "... ..."，中间用英文逗号连接。
    """
    try:
        sel_start_index = output_text.index(tk.SEL_FIRST)
        sel_end_index = output_text.index(tk.SEL_LAST)
    except tk.TclError:
        messagebox.showwarning('提示', '请先用鼠标选中要合并的两个或多个小段')
        return

    content = output_text.get('1.0', 'end-1c')
    sel_start = text_index_to_char_offset(sel_start_index)
    sel_end = text_index_to_char_offset(sel_end_index)

    if sel_end <= sel_start:
        messagebox.showwarning('提示', '请先用鼠标选中要合并的两个或多个小段')
        return

    segments = get_editable_segments_from_content(content)

    selected = []

    for seg in segments:
        # 只要选区碰到这个小段，就把整个小段纳入合并
        if seg['end'] > sel_start and seg['start'] < sel_end:
            selected.append(seg)

    if len(selected) < 2:
        messagebox.showwarning('提示', '至少需要选中两个小段才能合并')
        return

    markers = []
    bodies = []
    first_inline_prefix = None

    for seg in selected:
        marker, inline_prefix, body = parse_segment_parts(seg['text'])

        if first_inline_prefix is None and inline_prefix:
            first_inline_prefix = inline_prefix

        if marker:
            markers.append(marker)

        if body:
            bodies.append(body)

    unique_markers = []
    for marker in markers:
        if marker not in unique_markers:
            unique_markers.append(marker)

    if len(unique_markers) > 1:
        messagebox.showwarning(
            '模式冲突',
            '选中的小段里有不同模式标记，不能直接合并。\n\n请先统一成同一种【1】【2】【3】，或者清除其中一个标记。'
        )
        return

    final_marker = unique_markers[0] if unique_markers else None
    merged_body = join_bodies_with_comma(bodies)
    merged_segment = wrap_segment_body_with_inline_prefix(merged_body, final_marker, first_inline_prefix)

    if not merged_segment:
        messagebox.showwarning('提示', '没有可合并的正文')
        return

    replace_start = selected[0]['start']
    replace_end = selected[-1]['end']

    # 记录合并位置，避免合并后 Text 控件自动跳回开头
    replace_start_index = char_offset_to_text_index(replace_start)
    replace_end_index = char_offset_to_text_index(replace_end)

    output_text.delete(replace_start_index, replace_end_index)
    output_text.insert(replace_start_index, merged_segment)

    # 合并后的结束位置
    merged_end_index = f'{replace_start_index}+{len(merged_segment)}c'

    sync_after_output_edit()
    clear_merge_pick_segments()

    # 延迟恢复视图，防止同步/刷新后又跳回开头
    def restore_after_merge():
        try:
            output_text.mark_set(tk.INSERT, merged_end_index)
            output_text.see(replace_start_index)
            output_text.focus_set()
        except:
            pass

    root.after(10, restore_after_merge)

    root.title(f'英文段落智能断行工具 - 已合并 {len(selected)} 个小段')




def get_preview_row_no_by_offset(content, offset):
    """根据字符位置判断它属于批量预览中的第几条。单条结果没有标题时返回 None。"""
    row_no = None

    for m in re.finditer(r'^=+\s*第\s*(\d+)\s*条\s*=+\s*$', content, re.M):
        if m.start() <= offset:
            row_no = int(m.group(1))
        else:
            break

    return row_no


def get_current_segment_index():
    """获取当前光标所在小段在全部可编辑小段中的序号。"""
    content = output_text.get('1.0', 'end-1c')
    segments = get_editable_segments_from_content(content)

    if not segments:
        return None

    cursor_offset = text_index_to_char_offset(tk.INSERT)
    seg = find_segment_by_offset(content, cursor_offset)

    if not seg:
        return None

    for index, item in enumerate(segments):
        if item['start'] == seg['start'] and item['end'] == seg['end']:
            return index

    return None


def refresh_merge_pick_highlights():
    """刷新非相邻合并选择高亮。"""
    try:
        output_text.tag_remove('merge_pick_highlight', '1.0', tk.END)
    except:
        pass

    content = output_text.get('1.0', 'end-1c')
    segments = get_editable_segments_from_content(content)
    valid_indices = []

    for index in merge_pick_indices:
        if 0 <= index < len(segments):
            seg = segments[index]
            output_text.tag_add(
                'merge_pick_highlight',
                char_offset_to_text_index(seg['start']),
                char_offset_to_text_index(seg['end'])
            )
            valid_indices.append(index)

    merge_pick_indices[:] = valid_indices

    try:
        merge_pick_info_label.config(text=f'已选 {len(merge_pick_indices)} 个')
    except:
        pass


def toggle_current_segment_merge_pick():
    """把当前小段加入/移出非相邻合并列表。"""
    index = get_current_segment_index()

    if index is None:
        messagebox.showwarning('提示', '请先把鼠标点到要加入合并的小段里面')
        return

    if index in merge_pick_indices:
        merge_pick_indices.remove(index)
    else:
        merge_pick_indices.append(index)
        merge_pick_indices.sort()

    refresh_merge_pick_highlights()
    root.title(f'英文段落智能断行工具 - 非相邻合并已选 {len(merge_pick_indices)} 个小段')


def clear_merge_pick_segments():
    """清空非相邻合并选择。"""
    merge_pick_indices.clear()

    try:
        output_text.tag_remove('merge_pick_highlight', '1.0', tk.END)
    except:
        pass

    try:
        merge_pick_info_label.config(text='已选 0 个')
    except:
        pass


def merge_picked_segments():
    """
    合并通过“加入合并选择”挑选的小段。
    可以是不相邻的小段；会合并到第一个被选小段的位置，其他被选小段会删除。
    """
    content = output_text.get('1.0', 'end-1c')
    segments = get_editable_segments_from_content(content)

    selected = []

    for index in merge_pick_indices:
        if 0 <= index < len(segments):
            selected.append(segments[index])

    if len(selected) < 2:
        messagebox.showwarning('提示', '请至少加入两个小段后再合并')
        return

    # 不允许跨“第 X 条”合并，避免复制批量结果时串到别的单元格
    row_set = set()
    for seg in selected:
        row_set.add(get_preview_row_no_by_offset(content, seg['start']))

    if len(row_set) > 1:
        messagebox.showwarning('提示', '不能跨不同的“第 X 条”合并，请只选择同一条里面的小段')
        return

    markers = []
    bodies = []
    first_inline_prefix = None

    for seg in selected:
        marker, inline_prefix, body = parse_segment_parts(seg['text'])

        if first_inline_prefix is None and inline_prefix:
            first_inline_prefix = inline_prefix

        if marker:
            markers.append(marker)

        if body:
            bodies.append(body)

    unique_markers = []
    for marker in markers:
        if marker not in unique_markers:
            unique_markers.append(marker)

    if len(unique_markers) > 1:
        messagebox.showwarning(
            '模式冲突',
            '选中的小段里有不同模式标记，不能直接合并。\n\n请先统一成同一种【1】【2】【3】，或者清除其中一个标记。'
        )
        return

    final_marker = unique_markers[0] if unique_markers else None
    merged_body = join_bodies_with_comma(bodies)
    merged_segment = wrap_segment_body_with_inline_prefix(merged_body, final_marker, first_inline_prefix)

    if not merged_segment:
        messagebox.showwarning('提示', '没有可合并的正文')
        return

    # 先在字符串里替换，处理非相邻段更稳定
    selected_sorted = sorted(selected, key=lambda x: x['start'])
    first_seg = selected_sorted[0]

    new_content = content

    for seg in sorted(selected_sorted, key=lambda x: x['start'], reverse=True):
        if seg is first_seg:
            replacement = merged_segment
        else:
            replacement = ''

        new_content = new_content[:seg['start']] + replacement + new_content[seg['end']:]

    # 清理被删除小段留下来的多余空行
    new_content = re.sub(r'\n{3,}', '\n\n', new_content).strip('\n')

    # 记录合并后要停留的位置，避免重写整个输出框后跳回开头
    restore_offset = first_seg['start']

    output_text.delete('1.0', tk.END)
    output_text.insert('1.0', new_content)

    clear_merge_pick_segments()
    sync_after_output_edit()

    # 延迟恢复视图，防止 Text 控件刷新后自动回到开头
    def restore_after_merge_picked():
        try:
            restore_index = char_offset_to_text_index(restore_offset)
            output_text.mark_set(tk.INSERT, restore_index)
            output_text.see(restore_index)
            output_text.focus_set()
        except:
            pass

    root.after(10, restore_after_merge_picked)

    root.title(f'英文段落智能断行工具 - 已合并 {len(selected_sorted)} 个非相邻小段')


def clear_search_highlights():
    """清除搜索高亮"""
    global search_matches, search_current_index

    try:
        output_text.tag_remove('search_highlight', '1.0', tk.END)
        output_text.tag_remove('search_current', '1.0', tk.END)
    except:
        pass

    search_matches = []
    search_current_index = -1

    try:
        search_info_label.config(text='')
    except:
        pass


def get_location_text_by_index(index):
    """根据搜索位置，显示大概在第几条、第几个小段"""
    try:
        content = output_text.get('1.0', 'end-1c')
        offset = text_index_to_char_offset(index)
    except:
        return ''

    # 找当前属于第几条批量预览
    row_no = None
    row_start = 0

    for m in re.finditer(r'^=+\s*第\s*(\d+)\s*条\s*=+\s*$', content, re.M):
        if m.start() <= offset:
            row_no = int(m.group(1))
            row_start = m.end()
        else:
            break

    # 统计这一条里面，当前是第几个有效小段
    seg_no = 0
    current_seg_no = None

    for seg in get_editable_segments_from_content(content):
        if seg['start'] < row_start:
            continue

        # 如果有下一条标题，超过当前 offset 后自然不继续强判断
        if row_no is not None:
            next_header = re.search(r'^=+\s*第\s*\d+\s*条\s*=+\s*$', content[seg['start']:], re.M)

        seg_no += 1

        if seg['start'] <= offset <= seg['end']:
            current_seg_no = seg_no
            break

        if seg['start'] > offset:
            break

    if row_no and current_seg_no:
        return f'第 {row_no} 条 / 第 {current_seg_no} 小段'

    if row_no:
        return f'第 {row_no} 条'

    if current_seg_no:
        return f'第 {current_seg_no} 小段'

    return ''


def goto_search_match(match_index):
    """跳到指定搜索结果"""
    global search_current_index

    if not search_matches:
        return

    if match_index < 0:
        match_index = len(search_matches) - 1

    if match_index >= len(search_matches):
        match_index = 0

    search_current_index = match_index

    output_text.tag_remove('search_current', '1.0', tk.END)

    start, end = search_matches[search_current_index]
    output_text.tag_add('search_current', start, end)
    output_text.mark_set(tk.INSERT, start)
    output_text.see(start)
    output_text.focus_set()

    location = get_location_text_by_index(start)

    if location:
        search_info_label.config(text=f'找到 {len(search_matches)} 处，当前第 {search_current_index + 1} 处｜{location}')
    else:
        search_info_label.config(text=f'找到 {len(search_matches)} 处，当前第 {search_current_index + 1} 处')


def normalize_for_loose_search(text):
    """
    宽松搜索用：忽略大小写、空格、标点、省略号、引号和【1】【2】【3】标记。
    例如原文 Do not close this video. Please stay for
    可以搜到断行后的 do not close this video.please stay for
    """
    text = text or ''
    text = MODE_MARK_RE.sub('', text)
    text = text.lower()

    # 常见断行包装和标点全部忽略
    text = text.replace('“', '')
    text = text.replace('”', '')
    text = text.replace('"', '')
    text = text.replace('...', '')
    text = text.replace('…', '')

    # 只保留英文和数字；空格、句号、逗号等全部忽略
    text = re.sub(r'[^a-z0-9]+', '', text)
    return text


def search_output_text(event=None):
    """搜索输出框文本并高亮。默认宽松搜索，能搜原文片段。"""
    global search_matches, search_current_index

    clear_search_highlights()

    keyword = search_entry.get().strip()

    if not keyword:
        search_info_label.config(text='请输入搜索词')
        return

    search_matches = []
    search_current_index = -1

    use_loose = True

    try:
        use_loose = bool(loose_search_var.get())
    except:
        use_loose = True

    if use_loose:
        loose_keyword = normalize_for_loose_search(keyword)

        if not loose_keyword:
            search_info_label.config(text='请输入可搜索的英文或数字')
            return

        content = output_text.get('1.0', 'end-1c')
        segments = get_editable_segments_from_content(content)

        for seg in segments:
            loose_seg = normalize_for_loose_search(seg['text'])

            if loose_keyword in loose_seg:
                start = char_offset_to_text_index(seg['start'])
                end = char_offset_to_text_index(seg['end'])
                output_text.tag_add('search_highlight', start, end)
                search_matches.append((start, end))
    else:
        start = '1.0'
        count_var = tk.IntVar()

        while True:
            pos = output_text.search(keyword, start, stopindex=tk.END, nocase=True, count=count_var)

            if not pos:
                break

            length = count_var.get()

            if length <= 0:
                break

            end = f'{pos}+{length}c'
            output_text.tag_add('search_highlight', pos, end)
            search_matches.append((pos, end))
            start = end

    if not search_matches:
        search_info_label.config(text='没有找到')
        return

    goto_search_match(0)


def next_search_result():
    """下一个搜索结果"""
    if not search_matches:
        search_output_text()
        return

    goto_search_match(search_current_index + 1)


def prev_search_result():
    """上一个搜索结果"""
    if not search_matches:
        search_output_text()
        return

    goto_search_match(search_current_index - 1)

def toggle_window_size():
    """切换窗口宽度：左边不动，只向右扩大/缩小"""

    global is_large_window

    root.update_idletasks()

    current_height = root.winfo_height()
    current_x = root.winfo_x()
    current_y = root.winfo_y()

    if is_large_window:
        new_width = SMALL_WIDTH
        toggle_size_btn.config(text="变大窗口")
        is_large_window = False
    else:
        new_width = LARGE_WIDTH
        toggle_size_btn.config(text="变小窗口")
        is_large_window = True

    # 左边位置不变，只改变宽度
    root.geometry(f"{new_width}x{current_height}+{current_x}+{current_y}")

def merge_short_tail_lines(lines):
    """把 Amen. / Amen! 这种特别短的结尾行合并到上一行"""

    if len(lines) < 2:
        return lines

    new_lines = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        lower = line.lower()

        # 如果当前行是很短的结尾句，比如 Amen.
        if (
            new_lines
            and len(line) <= VERY_SHORT_LEN
            and (
                lower in ["amen.", "amen!", "amen"]
                or lower.startswith("amen.")
                or lower.startswith("amen!")
            )
        ):
            # 合并到上一行
            new_lines[-1] = new_lines[-1] + JOIN_SPACE + line
        else:
            new_lines.append(line)

    return new_lines



# 创建窗口
root = tk.Tk()
root.title("英文段落智能断行工具")

# ===== 窗口居中 =====
window_width = SMALL_WIDTH
window_height = WINDOW_HEIGHT

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

x = int((screen_width - window_width) / 2)
y = int((screen_height - window_height) / 2)

root.geometry(f"{window_width}x{window_height}+{x}+{y}")
# ===================

# 允许拖拽调整大小
root.resizable(True, True)

# 顶部按钮区域
button_frame = tk.Frame(root)
button_frame.pack(fill=tk.X, padx=10, pady=5)

paste_btn = tk.Button(
    button_frame,
    text="粘贴",
    width=10,
    command=paste_text
)
paste_btn.pack(side=tk.LEFT, padx=3)

run_btn = tk.Button(
    button_frame,
    text="运行",
    width=10,
    command=split_sentences
)
run_btn.pack(side=tk.LEFT, padx=3)

batch_sheet_btn = tk.Button(
    button_frame,
    text="粘贴批量并处理",
    width=16,
    command=paste_batch_from_sheet
)
batch_sheet_btn.pack(side=tk.LEFT, padx=3)

copy_batch_btn = tk.Button(
    button_frame,
    text="复制批量结果",
    width=14,
    command=copy_batch_results
)
copy_batch_btn.pack(side=tk.LEFT, padx=3)

batch_csv_btn = tk.Button(
    button_frame,
    text="导入CSV批量处理",
    width=16,
    command=batch_process_csv
)
batch_csv_btn.pack(side=tk.LEFT, padx=3)

toggle_size_btn = tk.Button(
    button_frame,
    text="变大窗口",
    width=10,
    command=toggle_window_size
)
toggle_size_btn.pack(side=tk.LEFT, padx=3)

# 输入框标题
input_label = tk.Label(root, text="输入内容：")
input_label.pack(anchor="w", padx=10)

# 输入框
input_text = scrolledtext.ScrolledText(
    root,
    wrap=tk.WORD,
    height=6,
    font=("Arial", 11)
)
input_text.pack(fill=tk.X, padx=10, pady=5)

# 输出区域标题和按钮
output_frame = tk.Frame(root)
output_frame.pack(fill=tk.X, padx=10)

output_label = tk.Label(
    output_frame,
    text="断行结果 / 批量预览："
)
output_label.pack(side=tk.LEFT)

copy_btn = tk.Button(
    output_frame,
    text="复制单条结果",
    width=14,
    command=copy_result
)
copy_btn.pack(side=tk.RIGHT)

add_space_btn = tk.Button(
    output_frame,
    text="每行加2空格",
    width=12,
    command=add_two_spaces
)
add_space_btn.pack(side=tk.RIGHT, padx=5)




# 断行字符数设置区域
length_frame = tk.Frame(root)
length_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

length_label = tk.Label(length_frame, text="断行设置：目标字符")
length_label.pack(side=tk.LEFT, padx=(0, 4))

target_len_entry = tk.Entry(length_frame, width=6)
target_len_entry.insert(0, str(PACK_TARGET_LEN))
target_len_entry.pack(side=tk.LEFT, padx=3)

max_len_label = tk.Label(length_frame, text="最大字符")
max_len_label.pack(side=tk.LEFT, padx=(8, 4))

max_len_entry = tk.Entry(length_frame, width=6)
max_len_entry.insert(0, str(MAX_LINE_LEN))
max_len_entry.pack(side=tk.LEFT, padx=3)

apply_len_btn = tk.Button(
    length_frame,
    text="应用设置",
    width=10,
    command=lambda: apply_length_settings(show_message=True)
)
apply_len_btn.pack(side=tk.LEFT, padx=6)

length_hint_label = tk.Label(
    length_frame,
    text="说明：先参考字符数，断开时优先 . ! ?，其次逗号，最后才按空格兜底",
    fg="#666"
)
length_hint_label.pack(side=tk.LEFT, padx=8)

# 搜索功能区域
search_frame = tk.Frame(root)
search_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

search_label = tk.Label(search_frame, text="搜索：")
search_label.pack(side=tk.LEFT)

search_entry = tk.Entry(search_frame, width=28)
search_entry.pack(side=tk.LEFT, padx=4)
search_entry.bind('<Return>', search_output_text)

loose_search_var = tk.IntVar(value=1)
loose_search_check = tk.Checkbutton(
    search_frame,
    text="宽松搜索",
    variable=loose_search_var
)
loose_search_check.pack(side=tk.LEFT, padx=2)

search_btn = tk.Button(
    search_frame,
    text="查找",
    width=8,
    command=search_output_text
)
search_btn.pack(side=tk.LEFT, padx=2)

prev_search_btn = tk.Button(
    search_frame,
    text="上一个",
    width=8,
    command=prev_search_result
)
prev_search_btn.pack(side=tk.LEFT, padx=2)

next_search_btn = tk.Button(
    search_frame,
    text="下一个",
    width=8,
    command=next_search_result
)
next_search_btn.pack(side=tk.LEFT, padx=2)

clear_search_btn = tk.Button(
    search_frame,
    text="清除高亮",
    width=10,
    command=clear_search_highlights
)
clear_search_btn.pack(side=tk.LEFT, padx=2)

search_info_label = tk.Label(search_frame, text="", fg="#666")
search_info_label.pack(side=tk.LEFT, padx=8)

# 小段编辑区域：拆分 / 合并
segment_edit_frame = tk.Frame(root)
segment_edit_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

segment_edit_label = tk.Label(
    segment_edit_frame,
    text="小段编辑："
)
segment_edit_label.pack(side=tk.LEFT, padx=(0, 8))

split_btn = tk.Button(
    segment_edit_frame,
    text="光标处拆分",
    width=12,
    command=lambda: split_current_segment(None)
)
split_btn.pack(side=tk.LEFT, padx=3)

split_mode1_btn = tk.Button(
    segment_edit_frame,
    text="拆分为【1】",
    width=11,
    bg="#fff7ed",
    command=lambda: split_current_segment("1")
)
split_mode1_btn.pack(side=tk.LEFT, padx=3)

split_mode2_btn = tk.Button(
    segment_edit_frame,
    text="拆分为【2】",
    width=11,
    bg="#eff6ff",
    command=lambda: split_current_segment("2")
)
split_mode2_btn.pack(side=tk.LEFT, padx=3)

split_mode3_btn = tk.Button(
    segment_edit_frame,
    text="拆分为【3】",
    width=11,
    bg="#fdf2f8",
    command=lambda: split_current_segment("3")
)
split_mode3_btn.pack(side=tk.LEFT, padx=3)

merge_segments_btn = tk.Button(
    segment_edit_frame,
    text="合并所选小段",
    width=14,
    command=merge_selected_segments
)
merge_segments_btn.pack(side=tk.LEFT, padx=3)

pick_merge_btn = tk.Button(
    segment_edit_frame,
    text="加入合并选择",
    width=13,
    command=toggle_current_segment_merge_pick
)
pick_merge_btn.pack(side=tk.LEFT, padx=3)

merge_picked_btn = tk.Button(
    segment_edit_frame,
    text="合并已选",
    width=10,
    command=merge_picked_segments
)
merge_picked_btn.pack(side=tk.LEFT, padx=3)

clear_picked_btn = tk.Button(
    segment_edit_frame,
    text="清空已选",
    width=10,
    command=clear_merge_pick_segments
)
clear_picked_btn.pack(side=tk.LEFT, padx=3)

merge_pick_info_label = tk.Label(segment_edit_frame, text="已选 0 个", fg="#666")
merge_pick_info_label.pack(side=tk.LEFT, padx=6)

# 小段模式标记按钮区域
mode_marker_frame = tk.Frame(root)
mode_marker_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

mode_marker_label = tk.Label(
    mode_marker_frame,
    text="小段模式标记：先点输出框里的某一小段，再点按钮；也可以选中多行后批量标记"
)
mode_marker_label.pack(side=tk.LEFT, padx=(0, 8))

mode1_btn = tk.Button(
    mode_marker_frame,
    text="【1】闭眼祷告",
    width=12,
    bg="#fff7ed",
    command=lambda: set_current_line_mode_marker("1")
)
mode1_btn.pack(side=tk.LEFT, padx=3)

mode2_btn = tk.Button(
    mode_marker_frame,
    text="【2】睁眼说话",
    width=12,
    bg="#eff6ff",
    command=lambda: set_current_line_mode_marker("2")
)
mode2_btn.pack(side=tk.LEFT, padx=3)

mode3_btn = tk.Button(
    mode_marker_frame,
    text="【3】闭眼流泪",
    width=12,
    bg="#fdf2f8",
    command=lambda: set_current_line_mode_marker("3")
)
mode3_btn.pack(side=tk.LEFT, padx=3)

clear_mode_btn = tk.Button(
    mode_marker_frame,
    text="清除标记",
    width=10,
    command=lambda: set_current_line_mode_marker(None)
)
clear_mode_btn.pack(side=tk.LEFT, padx=3)

# 小段前缀功能区域
prefix_frame = tk.Frame(root)
prefix_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

prefix_label = tk.Label(
    prefix_frame,
    text="小段前缀："
)
prefix_label.pack(side=tk.LEFT, padx=(0, 4))

segment_prefix_entry = tk.Entry(prefix_frame, width=10)
segment_prefix_entry.insert(0, "oh")
segment_prefix_entry.pack(side=tk.LEFT, padx=3)

prefix_all_btn = tk.Button(
    prefix_frame,
    text="全部小段加前缀",
    width=14,
    command=lambda: apply_inline_prefix_to_segments(selected_only=False, remove=False)
)
prefix_all_btn.pack(side=tk.LEFT, padx=3)

prefix_selected_btn = tk.Button(
    prefix_frame,
    text="选中/当前加前缀",
    width=15,
    command=lambda: apply_inline_prefix_to_segments(selected_only=True, remove=False)
)
prefix_selected_btn.pack(side=tk.LEFT, padx=3)

clear_prefix_btn = tk.Button(
    prefix_frame,
    text="清除前缀",
    width=10,
    command=lambda: apply_inline_prefix_to_segments(selected_only=False, remove=True)
)
clear_prefix_btn.pack(side=tk.LEFT, padx=3)

# 输出框
output_text = scrolledtext.ScrolledText(
    root,
    wrap=tk.WORD,
    font=("Arial", 11)
)
output_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

output_text.tag_config('search_highlight', background='#fff59d')
output_text.tag_config('search_current', background='#ffb74d')
output_text.tag_config('merge_pick_highlight', background='#d9f99d')

root.mainloop()
