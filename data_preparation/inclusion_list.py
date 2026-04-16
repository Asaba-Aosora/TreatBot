import pandas as pd
import re

# ---------- 字段提取函数 ----------
def extract_age(text):
    """提取最小和最大年龄，返回 (min_age, max_age)"""
    # 按句号、分号、换行分割句子
    sentences = re.split(r'[，。；\n]', text)
    for sent in sentences:
        # 去除句子开头的序号（如“2、”“2.”“2 ”等）
        sent_clean = re.sub(r'^\s*\d+[、.\s)]*', '', sent).strip()
        sent_clean = re.sub(r'[\(（][^\)）]*[\)）]', '', sent_clean).strip() # 去除括号内的内容
        if not sent_clean:
            continue
        # 判断是否可能包含年龄信息（必须有年龄相关词或比较符号）
        if not re.search(r'年龄|年满|岁|周岁', sent_clean):
            continue

        # 匹配完整范围：两个数字之间有连接词（且、并、和、至、-、~等）
        m = re.search(r'[≥>]?\s*(\d+)\s*(?:岁|周岁)?\s*[且并、至～~-]\s*[≤<]?\s*(\d+)', sent_clean)
        if m:
            return int(m.group(1)), int(m.group(2))

        # 只有下限（有≥或>）
        m = re.search(r'[≥>]\s*(\d+)', sent_clean)
        if m:
            return int(m.group(1)), None

        # 只有上限（有≤或<）
        m = re.search(r'[≤<]\s*(\d+)', sent_clean)
        if m:
            return None, int(m.group(1))

        # 如果句子中有数字后跟“岁”，但没有比较符号，视为下限（如“年满18岁”）
        m = re.search(r'(\d+)\s*岁', sent_clean)
        if m:
            return int(m.group(1)), None

        # 如果句子中有“≥”但没有数字？忽略
    return None, None

def extract_gender(text):
    # 分割句子（以。；！？\n等分割）
    sentences = re.split(r'[。；！？\n]', text)
    # 只考虑前3个句子
    for sent in sentences[:3]:
        if '性别不限' in sent or '男女不限' in sent or '男性或女性' in sent:
            return '不限'
        if '男性' in sent and '女性' not in sent:
            return '男'
        if '女性' in sent and '男性' not in sent:
            return '女'
    # 如果前3句没有明确，则全局搜索但不处理同时出现的情况
    if re.search(r'性别不限|男女不限', text):
        return '不限'
    # 如果同时出现男性和女性，无法判断，返回None
    if re.search(r'男性', text) and re.search(r'女性', text):
        return None
    if re.search(r'男性', text):
        return '男'
    if re.search(r'女性', text):
        return '女'
    return None

def extract_ecog(text):
    """
    提取ECOG最小值和最大值，返回 (ecog_min, ecog_max)
    """
    sentences = re.split(r'[。；\n]', text)
    for sent in sentences:
        # 检查是否包含ECOG相关关键词
        if not re.search(r'ECOG|东部肿瘤协作组', sent):
            continue
        sent_clean = re.sub(r'^\s*\d+[、.\s)]*', '', sent).strip()
        if not sent_clean:
            continue

        # 1. 匹配“X或Y”、“X/Y”（X和Y可以是数字）
        m = re.search(r'(\d+)\s*[或/]\s*(\d+)', sent_clean)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return min(a, b), max(a, b)

        # 2. 匹配范围“X-Y”、“X~Y”、“X到Y”
        m = re.search(r'(\d+)\s*[～~\-到]\s*(\d+)', sent_clean)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return min(a, b), max(a, b)

        # 3. 匹配≤X或<X（通常≤X表示允许0到X）
        m = re.search(r'[≤<]\s*(\d+)', sent_clean)
        if m:
            max_val = int(m.group(1))
            return 0, max_val

        # 4. 匹配≥X或>X（罕见，如ECOG≥2）
        m = re.search(r'[≥>]\s*(\d+)', sent_clean)
        if m:
            min_val = int(m.group(1))
            return min_val, 5  # 假设最大值为5

        # 5. 匹配单个数字（如“ECOG 0分”），默认允许0到该值
        m = re.search(r'(\d+)', sent_clean)
        if m:
            num = int(m.group(1))
            return 0, num

    return None, None

def extract_survival(text):
    m = re.search(r'[预期预计]*生存期.*?[≥>]?\s*(\d+)', text)
    if m:
        return int(m.group(1))
    return None

# ---------- 分期-癌种拆分 ----------
def parse_failure_criteria(text, trial_id):
    entries = []
    phase_pattern = re.compile(
        r'^([ⅠI1][a-zA-Z/0-9]*期|[ⅠI1][bB]/[ⅡII2]+期)\s*需满足[：:]', 
        re.MULTILINE
    )
    parts = re.split(phase_pattern, text)
    
    if len(parts) == 1:
        content = text
        cancer_pattern = r'([①②③④⑤⑥⑦⑧⑨⑩])\s*([^：]+)[：:]([^①②③④⑤⑥⑦⑧⑨⑩]+)'
        for num, cancer_name, condition in re.findall(cancer_pattern, content, flags=re.DOTALL):
            entries.append({
                '项目编码': trial_id,
                '期数': '',
                '癌症种类': cancer_name.strip(),
                '准入条件': condition.strip()
            })
    else:
        for i in range(1, len(parts), 2):
            phase = parts[i].strip()
            content = parts[i+1].strip()
            cancer_pattern = r'([①②③④⑤⑥⑦⑧⑨⑩])\s*([^：]+)[：:]([^①②③④⑤⑥⑦⑧⑨⑩]+)'
            for num, cancer_name, condition in re.findall(cancer_pattern, content, flags=re.DOTALL):
                entries.append({
                    '项目编码': trial_id,
                    '期数': phase,
                    '癌症种类': cancer_name.strip(),
                    '准入条件': condition.strip()
                })
    return entries

# ---------- 处理单行 ----------
def process_trial(row):
    trial_id = row['项目编码']
    text = row['入组条件']
    if pd.isna(text):
        text = ''
    
    age_min, age_max = extract_age(text)
    gender = extract_gender(text)
    ecog_min, ecog_max = extract_ecog(text)
    survival = extract_survival(text)
    
    main_row = {
        '项目编码': trial_id,
        '最小年龄': age_min,
        '最大年龄': age_max,
        '性别': gender,
        'ECOG_min': ecog_min,
        'ECOG_max': ecog_max,
        '最短预计生存期': survival
    }
    
    split_entries = parse_failure_criteria(text, trial_id)
    return main_row, split_entries

# ---------- 主程序 ----------
def main(input_file, output_file):
    # 1. 读取Excel的所有sheet，返回{sheet名: DataFrame}的字典
    try:
        all_sheets = pd.read_excel(input_file, sheet_name=None, dtype=str)
    except Exception as e:
        raise ValueError(f"读取Excel文件失败: {str(e)}")
    
    # 初始化存储所有sheet处理结果的列表
    all_main_rows = []
    all_split_rows = []
    
    # 2. 遍历每个sheet进行处理
    for sheet_name, df in all_sheets.items():
        print(f"正在处理sheet: {sheet_name}")
        
        # 检查当前sheet是否包含必填列
        required_cols = ['项目编码', '入组条件']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Sheet [{sheet_name}] 缺少必填列: {', '.join(missing_cols)}")
        
        # 3. 处理当前sheet的每一行数据
        for idx, row in df.iterrows():
            try:
                main_row, split_entries = process_trial(row)
                # 可选：添加sheet名称字段，方便追溯数据来源
                main_row['数据来源sheet'] = sheet_name
                for entry in split_entries:
                    entry['数据来源sheet'] = sheet_name
                
                all_main_rows.append(main_row)
                all_split_rows.extend(split_entries)
            except Exception as e:
                raise RuntimeError(f"处理Sheet [{sheet_name}] 第{idx+1}行数据失败: {str(e)}")
    
    # 4. 合并所有sheet的处理结果并写入输出文件
    main_df = pd.DataFrame(all_main_rows)
    split_df = pd.DataFrame(all_split_rows)
    
    with pd.ExcelWriter(output_file) as writer:
        main_df.to_excel(writer, sheet_name='试验提取字段', index=False)
        split_df.to_excel(writer, sheet_name='失败标准拆分', index=False)
    
    print(f"所有sheet处理完成！共处理 {len(all_sheets)} 个sheet，结果已保存至: {output_file}")


if __name__ == "__main__":
    input_file = "original_data/clinical_trials/临床试验数据20250908-原始数据.xlsx"   # 请修改为实际路径
    output_file = "structured_data/临床试验_入组条件_结构化结果.xlsx"
    main(input_file, output_file)