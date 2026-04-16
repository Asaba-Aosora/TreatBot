import re
import pandas as pd

def extract_lines_min(text):
    """
    从准入条件文本中提取最小治疗线数（整数）。
    规则：
    1. 优先匹配包含修饰符（≥、>、至少、不少于、不低于）或范围（至、-、~）的线数描述；
    2. 若无，再匹配单纯的“X线”或“XL”，但只取 X≥2 的值（避免误提取“1线标准治疗”等描述）；
    3. 返回所有匹配中的最小值，若无则返回 None。
    """
    if not isinstance(text, str):
        return None

    # 中文数字映射
    chinese_map = {'一':1, '二':2, '三':3, '四':4, '五':5,
                   '六':6, '七':7, '八':8, '九':9, '十':10}

    def to_int(s):
        if s in chinese_map:
            return chinese_map[s]
        try:
            return int(s)
        except:
            return None

    # 定义正则模式（忽略大小写以匹配 L 或 l）
    # 1. 范围：如“2-3线”、“二至三线”
    range_arabic = re.compile(r'(\d+)\s*[至~-]\s*\d+\s*(?:线|L)', re.IGNORECASE)
    range_chinese = re.compile(r'([一二三四五六七八九十])\s*[至~-]\s*[一二三四五六七八九十]\s*(?:线|L)', re.IGNORECASE)
    # 2. 带修饰符的单值：如“≥2线”、“至少三线”
    single_mod_arabic = re.compile(r'(?:≥|>|至少|不少于|不低于)\s*(\d+)\s*(?:线|L)', re.IGNORECASE)
    single_mod_chinese = re.compile(r'(?:≥|>|至少|不少于|不低于)\s*([一二三四五六七八九十])\s*(?:线|L)', re.IGNORECASE)
    # 3. 无修饰符的单值：如“2线”、“二线”
    single_plain_arabic = re.compile(r'(\d+)\s*(?:线|L)', re.IGNORECASE)
    single_plain_chinese = re.compile(r'([一二三四五六七八九十])\s*(?:线|L)', re.IGNORECASE)

    candidates = []

    # 优先处理范围和带修饰符的（这些最可能是线数要求）
    for pattern in [range_arabic, range_chinese, single_mod_arabic, single_mod_chinese]:
        matches = pattern.findall(text)
        for match in matches:
            if isinstance(match, tuple):
                num_str = match[0]      # 范围模式取第一个数字
            else:
                num_str = match
            num = to_int(num_str)
            if num is not None:
                candidates.append(num)

    if candidates:
        return min(candidates)

    # 若无明确修饰符，再尝试无修饰符的单值，但只保留 X≥2
    for pattern in [single_plain_arabic, single_plain_chinese]:
        matches = pattern.findall(text)
        for num_str in matches:
            num = to_int(num_str)
            if num is not None and num >= 2:
                candidates.append(num)

    return min(candidates) if candidates else None


def main():
    # 读取原始Excel（请根据实际文件名和sheet名修改）
    input_file = 'structured_data/临床试验_入组条件_结构化结果.xlsx'          # 你的文件
    sheet_name = '失败标准拆分'                # 你的sheet名
    df = pd.read_excel(input_file, sheet_name=sheet_name)

    # 确保“准入条件”列存在
    if '准入条件' not in df.columns:
        raise ValueError("Excel中缺少“准入条件”列")

    # 提取lines_min
    df['lines_min'] = df['准入条件'].apply(extract_lines_min)

    with pd.ExcelWriter(input_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)


if __name__ == '__main__':
    main()