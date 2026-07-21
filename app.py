import streamlit as st
import pandas as pd
import re
import os
import io
from datetime import datetime

# ==================== 密码验证配置 ====================
# 密码从 Streamlit Secrets 读取，本地开发可在 .streamlit/secrets.toml 中设置
# [app]
# password = "your_password"
def get_app_password():
    try:
        return st.secrets["app"]["password"]
    except Exception:
        import os
        return os.environ.get('APP_PASSWORD', 'admin123')

# ==================== 生肖配置（2026年马年规则） ====================
ZODIAC_NUMBERS = {
    '鼠': ['07', '19', '31', '43'],
    '牛': ['06', '18', '30', '42'],
    '虎': ['05', '17', '29', '41'],
    '兔': ['04', '16', '28', '40'],
    '龙': ['03', '15', '27', '39'],
    '蛇': ['02', '14', '26', '38'],
    '马': ['01', '13', '25', '37', '49'],
    '羊': ['12', '24', '36', '48'],
    '猴': ['11', '23', '35', '47'],
    '鸡': ['10', '22', '34', '46'],
    '狗': ['09', '21', '33', '45'],
    '猪': ['08', '20', '32', '44']
}

ZODIAC_LIST = ['鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪']

# 号码到生肖的映射（用于反向查找）
NUMBER_TO_ZODIAC = {}
for zodiac, numbers in ZODIAC_NUMBERS.items():
    for num in numbers:
        NUMBER_TO_ZODIAC[num] = zodiac

# ==================== 赔率配置（完整赔率表） ====================
ODDS_TABLE = {
    # 基础玩法
    '特码': 47,
    '特肖': 11,
    '一肖': 2,
    '尾数': 1.8,
    '平码': 6,
    # 平码组合玩法
    '平码二中二': 60,
    '平码三中三': 600,
    '平码三中二': 20,
    # 自选不中（五不中至十二不中）
    '五不中': 2,
    '六不中': 2.5,
    '七不中': 3,
    '八不中': 3.5,
    '九不中': 4,
    '十不中': 5,
    '十一不中': 6,
    '十二不中': 7,
    # 连肖
    '二连肖': 4,
    '三连肖': 10,
    '四连肖': 30,
    '五连肖': 100,
    # 组合玩法
    '三中二': 20,
    '三全中': 600,
    '二全中': 60,
    '二中特': 20,
    '特中': 10,
}

# ==================== 尾数对应号码表 ====================
TAIL_NUMBERS = {
    '0': ['10', '20', '30', '40'],
    '1': ['01', '11', '21', '31', '41'],
    '2': ['02', '12', '22', '32', '42'],
    '3': ['03', '13', '23', '33', '43'],
    '4': ['04', '14', '24', '34', '44'],
    '5': ['05', '15', '25', '35', '45'],
    '6': ['06', '16', '26', '36', '46'],
    '7': ['07', '17', '27', '37', '47'],
    '8': ['08', '18', '28', '38', '48'],
    '9': ['09', '19', '29', '39', '49'],
}

# ==================== 数据解析函数 ====================

# 中文数字映射表
CN_NUM_MAP = {'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
              '十一':11,'十二':12,'二十':20,'三十':30,'四十':40,'五十':50,'六十':60,'七十':70,
              '八十':80,'九十':90,'一百':100,'一千':1000,'两千':2000,'四千':4000}

def cn_to_num(text):
    """将中文数字转换为阿拉伯数字"""
    text = text.strip()
    if text in CN_NUM_MAP:
        return CN_NUM_MAP[text]
    # 处理"一百五十"这类复合数字（一百+五十=150）
    if '百' in text:
        parts = text.split('百')
        if len(parts) == 2:
            hundred_part = parts[0]
            rest_part = parts[1]
            hundred_val = CN_NUM_MAP.get(hundred_part, 1) * 100 if hundred_part else 100
            rest_val = cn_to_num(rest_part) if rest_part else 0
            return hundred_val + rest_val
    # 处理"四十"这类
    if len(text) == 2 and text[0] in CN_NUM_MAP and text[1] == '十':
        return CN_NUM_MAP[text[0]] * 10
    # 处理"四十五"这类
    if len(text) >= 2 and text[0] in CN_NUM_MAP and text[1] == '十':
        rest = text[2:] if len(text) > 2 else ''
        base = CN_NUM_MAP[text[0]] * 10
        if rest and rest in CN_NUM_MAP:
            return base + CN_NUM_MAP[rest]
        return base
    # 纯数字
    nums = re.findall(r'(\d+)', text)
    if nums:
        return int(nums[0])
    return 0

def parse_amount(text):
    """
    从文本中提取金额数字，支持元、米、块等单位
    支持中文数字（四十、一百、四千等）
    支持中文复合数字（二十五、三十、一百等）
    支持"各十"、"各五十"等格式
    """
    text = text.strip()
    # 去除单位和修饰词
    text = text.replace('米', '').replace('块', '').replace('元', '')
    text = text.replace('各', '').replace('每组', '').replace('每个', '').replace('每号', '')
    # 先尝试解析中文数字（包括复合数字如二十五）
    amount = cn_to_num(text)
    if amount > 0:
        return amount
    # 尝试纯数字
    nums = re.findall(r'(\d+)', text)
    if nums:
        return int(nums[-1])
    return 0

def clean_line_prefix(line):
    """
    清理行首前缀：新奥、新澳、澳门特、澳特等
    返回清理后的行
    """
    prefixes = ['新奥', '新澳', '澳门特', '澳特', '老澳门', '澳门', '香港', '新澳门']
    for p in prefixes:
        if line.startswith(p):
            line = line[len(p):].strip()
            # 去除前缀后的逗号、顿号等
            line = line.lstrip('，,、:： ')
    return line

def expand_zodiac_to_numbers(zodiac, amount, bet_type, play_type, line_num):
    """
    将生肖展开成对应的号码列表
    参数：
        zodiac: 生肖名称（如'龙'）
        amount: 投注金额
        bet_type: 投注类型（特码/平码）
        play_type: 玩法名称
        line_num: 行号（用于追踪来源）
    返回：
        展开后的号码投注列表
    """
    results = []
    if zodiac in ZODIAC_NUMBERS:
        numbers = ZODIAC_NUMBERS[zodiac]
        for num in numbers:
            results.append({
                '号码': num,           # 必须是数字字符串（01-49）
                '金额': amount,        # 投注金额
                '类型': bet_type,      # 特码/平码
                '玩法': play_type,     # 具体玩法名称
                '投注对象': zodiac,    # 原始投注对象（生肖）
                '行号': line_num       # 原始行号
            })
    return results

def add_bet(results, num, amount, bet_type, play_type, obj, line_num):
    """辅助函数：添加一条投注记录"""
    results.append({
        '号码': num,
        '金额': amount,
        '类型': bet_type,
        '玩法': play_type,
        '投注对象': obj,
        '行号': line_num
    })

def parse_bet_input(text):
    """
    解析投注输入，支持多种真实用户写法
    关键规则：
    1. 没有标注'平码'的全部默认为特码
    2. 米=元，块=元
    3. 新奥、新澳、澳门特等前缀忽略
    4. 同一个号码在不同行出现时要累加
    5. 支持多行分段格式：玩法名称单独一行，下一行是号码+金额
    """
    text = text.strip()
    if not text:
        return [], []

    results = []
    errors = []
    zodiac_chars = ''.join(ZODIAC_LIST)

    lines = text.split('\n')

    # ====== 预处理：合并多行分段格式 ======
    # 格式：玩法名称单独一行（如"复试三中三"），下一行是号码+金额
    # 将这种格式合并为一行，并调整为"号码+玩法+金额"顺序
    # 同时统一分隔符：将 - 转换为 . 便于后续解析
    processed_lines = []
    i = 0
    
    # 玩法名称列表（提前定义，用于前缀行判断）
    play_patterns = ['三中三', '复试三中三', '复式三中三', '二中二', '复试二中二', '复式二中二',
                     '三连肖', '二连肖', '四连肖', '五连肖', '六连肖', '3中三', '3🀄️3',
                     '五不中', '六不中', '七不中', '八不中', '九不中', '十不中', '十一不中', '十二不中',
                     '复试3中三', '复试3中3', '复式3中三', '复式3中3']
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # 统一分隔符：将 - 转换为 .
        line = line.replace('-', '.')
        
        # 跳过汇总行（共X米、共X）
        if re.match(r'^共[\d一二三四五六七八九十百千]+(?:[米块元])?', line):
            i += 1
            continue
        
        # 跳过无意义行（ok、帮我买、计算结果等）
        if line.lower() in ['ok', 'okk', 'okok'] or '帮我买' in line or '=' in line and '+' in line:
            i += 1
            continue
        
        # 判断是否是前缀行（新奥、澳门特等，只有前缀）
        prefixes = ['新奥', '新澳', '澳门特', '澳特', '老澳门', '澳门', '香港', '新澳门']
        is_prefix_line = False
        matched_prefix = ''
        for p in prefixes:
            rest = line[len(p):].strip()
            if line == p or rest in ['', '，', ',', '、']:
                is_prefix_line = True
                matched_prefix = p
                break
            # 前缀+玩法名称（如"新奥 复试三中三"），后面需要合并号码行
            elif rest and any(rest.startswith(pp) for pp in ['复试三中三', '复式三中三', '复试二中二', '复式二中二']):
                is_prefix_line = True
                matched_prefix = line
                break
        
        if is_prefix_line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line:
                next_line = next_line.replace('-', '.')
                processed_lines.append(matched_prefix + ' ' + next_line)
                i += 2
                continue
        
        # 判断是否是玩法名称行（只有玩法名称，没有号码）
        is_play_line = False
        matched_play = ''
        for pattern in play_patterns:
            if line == pattern or line.startswith(pattern):
                is_play_line = True
                matched_play = pattern
                break
        
        if is_play_line and i + 1 < len(lines):
            # 下一行应该是号码+金额，或者是括号组格式
            next_line = lines[i + 1].strip()
            if next_line:
                # 统一分隔符：将 - 转换为 .
                next_line = next_line.replace('-', '.')
                # 检查是否是括号组格式
                if '【' in next_line or '[' in next_line or '（' in next_line or '(' in next_line:
                    # 括号组格式：需要合并后续所有括号组行和金额行
                    all_groups = next_line
                    j = i + 2
                    while j < len(lines):
                        next_next_line = lines[j].strip()
                        if not next_next_line:
                            j += 1
                            continue
                        next_next_line = next_next_line.replace('-', '.')
                        # 如果是括号组，继续合并
                        if '【' in next_next_line or '[' in next_next_line or '（' in next_next_line or '(' in next_next_line:
                            all_groups += ' ' + next_next_line
                            j += 1
                        # 如果是金额行（每组各、每组、各、共X），合并后结束
                        elif '每组' in next_next_line or '各' in next_next_line or '共' in next_next_line:
                            all_groups += ' ' + next_next_line
                            j += 1
                            break
                        else:
                            break
                    # 合并并调整顺序：括号组 + 金额 + 玩法
                    processed_lines.append(all_groups + ' ' + matched_play)
                    i = j
                    continue
                else:
                    # 普通格式：号码 + 玩法 + 金额
                    processed_lines.append(next_line + ' ' + matched_play)
                    i += 2
                    continue
        
        processed_lines.append(line)
        i += 1

    for line_num, line in enumerate(processed_lines, 1):
        line = line.strip()
        if not line:
            continue

        # 保存原始行，用于判断是否有澳门特/测门特/特肖前缀
        original_line = line

        # 清理前缀（新奥、新澳、澳门特等）
        line = clean_line_prefix(line)

        # 判断是否平码
        is_pingma = '平码' in line or '平特' in line
        bet_type = '平码' if is_pingma else '特码'

        # ====== 格式1：特：18=20米（特码标注） ======
        tema_eq_match = re.match(r'特[:：]\s*(\d{1,2})\s*=\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if tema_eq_match:
            num = tema_eq_match.group(1)
            amount = parse_amount(tema_eq_match.group(2))
            num_str = str(int(num)).zfill(2)
            if 1 <= int(num) <= 49:
                add_bet(results, num_str, amount, '特码', '特码', num_str, line_num)
            else:
                errors.append(f'号码{num}不在01-49范围内，已忽略')
            continue

        # ====== 格式1b：单号 号码=金额（单号 49=20 / 单号49=20，支持有无空格） ======
        danhao_eq_match = re.match(r'^单号\s*(\d{1,2})\s*=\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if danhao_eq_match:
            num = danhao_eq_match.group(1)
            amount = parse_amount(danhao_eq_match.group(2))
            num_str = str(int(num)).zfill(2)
            if 1 <= int(num) <= 49:
                add_bet(results, num_str, amount, bet_type, '平码' if is_pingma else '特码', num_str, line_num)
            else:
                errors.append(f'号码{num}不在01-49范围内，已忽略')
            continue

        # ====== 格式2：号码=金额（47=30, 22=30米, 01=25米） ======
        eq_match = re.match(r'^(\d{1,2})\s*=\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if eq_match:
            num = eq_match.group(1)
            amount = parse_amount(eq_match.group(2))
            num_str = str(int(num)).zfill(2)
            if 1 <= int(num) <= 49:
                add_bet(results, num_str, amount, bet_type, '平码' if is_pingma else '特码', num_str, line_num)
            else:
                errors.append(f'号码{num}不在01-49范围内，已忽略')
            continue

        # ====== 格式3：连肖组合（三连，兔龙牛，30）支持平码后缀 ======
        # 规则：连肖不展开，1组算1笔
        lianxiao_match = re.match(r'[\d一二三四五六七八九十]+连[，,]\s*([' + zodiac_chars + r']+)[，,]\s*([\d一二三四五六七八九十百千元米块]+)(平码)?', line)
        if lianxiao_match:
            zodiacs = lianxiao_match.group(1)
            amount = parse_amount(lianxiao_match.group(2))
            bet_type2 = '平码' if lianxiao_match.group(3) else '特码'
            play_name = f'{len(zodiacs)}连肖'
            zodiac_list = re.findall(r'([' + zodiac_chars + r'])', zodiacs)
            if zodiac_list:
                add_bet(results, ','.join(zodiac_list), amount, bet_type2, play_name, ','.join(zodiac_list), line_num)
            continue
        
        # ====== 格式4：三连肖：兔龙猴50 ======
        # 规则：连肖不展开，1组算1笔
        lianxiao2_match = re.match(r'连肖[:：]\s*([' + zodiac_chars + r']+)([\d一二三四五六七八九十百千元米块]+)', line)
        if lianxiao2_match:
            zodiacs = lianxiao2_match.group(1)
            amount = parse_amount(lianxiao2_match.group(2))
            play_name = f'{len(zodiacs)}连肖'
            zodiac_list = re.findall(r'([' + zodiac_chars + r'])', zodiacs)
            if zodiac_list:
                add_bet(results, ','.join(zodiac_list), amount, '特码', play_name, ','.join(zodiac_list), line_num)
            continue
        
        # ====== 格式5：狗平特500 ======
        # 规则：平特/特肖开头的投注不展开成号码，只算1笔
        pingte_match = re.match(r'([' + zodiac_chars + r'])平特([\d一二三四五六七八九十百千元米块]+)', line)
        if pingte_match:
            zodiac = pingte_match.group(1)
            amount = parse_amount(pingte_match.group(2))
            add_bet(results, zodiac, amount, '平码', '平特一肖', zodiac, line_num)
            continue
        
        # ====== 格式6：澳特：21，26，23各5米 ======
        aote_match = re.match(r'澳特[:：]\s*(.+)$', line)
        if aote_match:
            content = aote_match.group(1)
            amount = parse_amount(content)
            nums = re.findall(r'(\d{1,2})', content)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '特码', '玩法': '特码',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式7：生肖+各+金额（龙，兔，各20 / 龙，蛇，各25 / 鸡各号三十） ======
        # 规则：各 = 展开成所有对应号码，每个号码算1笔
        # 支持中文金额（各三十、各一百等）
        zodiac_ge_match = re.match(r'([' + zodiac_chars + r'，,、\s]+)各([\d一二三四五六七八九十百千元米块]+)', line)
        if zodiac_ge_match:
            zodiac_str = zodiac_ge_match.group(1)
            amount = parse_amount(zodiac_ge_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            # 各格式：展开成所有对应号码，每个号码算1笔
            for z in zodiacs:
                results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            continue

        # ====== 格式7b：生肖+各号+金额（虎，兔各号30米 / 牛猪兔羊鸡虎各号5 / 澳门特，虎，兔各号30米） ======
        # 规则：各号 = 展开成所有对应号码，每个号码算1笔
        # 支持同一行空格分隔的多段投注（如"猴虎狗鸡蛇牛各号30米 兔鼠各15米"）
        # 支持中文金额（各号三十、各号一百等）
        zodiac_gehao_match = re.match(r'([' + zodiac_chars + r'，,、\s]+)各号([\d一二三四五六七八九十百千元米块]+)', line)
        if zodiac_gehao_match:
            zodiac_str = zodiac_gehao_match.group(1)
            amount = parse_amount(zodiac_gehao_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            # 各号格式：展开成所有对应号码，每个号码算1笔
            for z in zodiacs:
                results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            # 检查是否有剩余部分（空格分隔的另一段投注，如"兔鼠各15米"）
            matched_end = zodiac_gehao_match.end()
            remaining = line[matched_end:].strip()
            # 去掉开头的单位字符（米/块/元）
            remaining = remaining.lstrip('米块元').strip()
            if remaining:
                remaining_results, remaining_errors = parse_bet_input(remaining)
                for r in remaining_results:
                    r['行号'] = line_num
                results.extend(remaining_results)
                errors.extend(remaining_errors)
            continue

        # ====== 格式8：生肖+每个+金额（鸡猴狗马每个5米 / 每个二十五） ======
        # 规则：每个 = 展开成所有对应号码，每个号码算1笔
        zodiac_meige_match = re.match(r'([' + zodiac_chars + r'，,、\s]+)每个([\d一二三四五六七八九十百千元米块]+)', line)
        if zodiac_meige_match:
            zodiac_str = zodiac_meige_match.group(1)
            amount = parse_amount(zodiac_meige_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            # 每个格式：展开成所有对应号码，每个号码算1笔
            for z in zodiacs:
                results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            continue

        # ====== 格式9：号码列表+各+金额（11.23.35各10 / 各五十 / 各十） ======
        num_ge_match = re.match(r'([\d.,，、\s]+)各([\d一二三四五六七八九十百千元米块]+)', line)
        if num_ge_match:
            nums_str = num_ge_match.group(1)
            amount = parse_amount(num_ge_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '特码', '玩法': '特码',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式9b：号码列表+各号+金额（6.9.11.13.16.17.22.24.26.41.44.49各号5 / 各号一百） ======
        num_gehao_match = re.match(r'([\d.,，、\s]+)各号([\d一二三四五六七八九十百千元米块]+)', line)
        if num_gehao_match:
            nums_str = num_gehao_match.group(1)
            amount = parse_amount(num_gehao_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '特码', '玩法': '特码',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式10：号码列表+每个+金额（22 35 33 25 17 48 26每个5米 / 每个二十五） ======
        num_meige_match = re.match(r'([\d.,，、\s]+)每个([\d一二三四五六七八九十百千元米块]+)', line)
        if num_meige_match:
            nums_str = num_meige_match.group(1)
            amount = parse_amount(num_meige_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '特码', '玩法': '特码',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式11：三中三（26.34.46三中三，十块 / 07.19.30，17.29.39，共2组每组50 三中三） ======
        # 规则：n个号码选3个的组合 = C(n,3)组，每组展开成3个号码，每个号码1笔
        # 支持两种金额格式：直接数字 和 "共X组每组Y"
        # 支持两种位置格式：号码+玩法+金额 和 号码+金额+玩法
        # 支持多组组合用逗号分隔：07.19.30，17.29.39，共2组每组50
        sanzhongsan_pattern = r'([\d.,，、\s]+)[，,]*([\d一二三四五六七八九十百千元米块]+|共[\d一二三四五六七八九十]+组每组[\d一二三四五六七八九十百千元米块]+|[\d]+组每组[\d一二三四五六七八九十百千元米块]+)[，,]*\s*(三中三|3中三|3🀄️3)?'
        sanzhongsan_match = re.match(sanzhongsan_pattern, line)
        if sanzhongsan_match and sanzhongsan_match.group(3):
            from itertools import combinations
            nums_str = sanzhongsan_match.group(1)
            amount_str = sanzhongsan_match.group(2)
            # 解析金额：支持"共X组每组Y"格式
            gezu_match = re.search(r'共(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', amount_str)
            if gezu_match:
                amount = parse_amount(gezu_match.group(2))
            else:
                amount = parse_amount(amount_str)
            # 按中文逗号分隔成多组号码
            groups = re.split(r'，', nums_str)
            all_valid_nums = []
            for group in groups:
                nums = re.findall(r'(\d{1,2})', group)
                valid_nums = []
                for n in nums:
                    if 1 <= int(n) <= 49:
                        valid_nums.append(str(int(n)).zfill(2))
                    else:
                        errors.append(f'号码{n}不在01-49范围内，已忽略')
                if valid_nums:
                    all_valid_nums.append(list(set(valid_nums)))
            if all_valid_nums and amount > 0:
                # 对每组号码计算三中三组合
                for valid_nums in all_valid_nums:
                    for combo in combinations(valid_nums, 3):
                        for num in combo:
                            add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue

        # ====== 格式12：复试/复试三中三/二中二（11.22.33.44复试三中三各3米 / 07.08.19.29.30.40，共20组每组10 复试三中三） ======
        # 规则：n个号码选m个的组合 = C(n,m)组，每组展开成m个号码，每个号码1笔
        # 支持两种金额格式：直接数字 和 "共X组每组Y"
        # 支持两种位置格式：号码+玩法+金额 和 号码+金额+玩法
        # 支持复试3中三格式
        fushi_pattern = r'([\d.,，、\s]+)[，,]*([\d一二三四五六七八九十百千元米块]+|共[\d一二三四五六七八九十]+组每组[\d一二三四五六七八九十百千元米块]+|[\d]+组每组[\d一二三四五六七八九十百千元米块]+)[，,]*\s*(复[试式](三中三|二中二|3中三))?'
        fushi_match = re.match(fushi_pattern, line)
        if fushi_match and fushi_match.group(4):
            from itertools import combinations
            nums_str = fushi_match.group(1)
            amount_str = fushi_match.group(2)
            play_cn = fushi_match.group(4)
            # 解析金额：支持"共X组每组Y"格式
            gezu_match = re.search(r'共(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', amount_str)
            if gezu_match:
                amount = parse_amount(gezu_match.group(2))
            else:
                amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if play_cn == '三中三' or play_cn == '3中三':
                play_name = '平码三中三'
                combo_size = 3
            else:
                play_name = '平码二中二'
                combo_size = 2
            if valid_nums and amount > 0:
                # 每个组合展开成combo_size个号码，每个号码算1笔
                for combo in combinations(valid_nums, combo_size):
                    for num in combo:
                        add_bet(results, num, amount, '平码', play_name, num, line_num)
            continue
        
        # ====== 格式12b：玩法名称在前-号码在后（复试三中三 01.07.08.10.11，共10组每组20 / 复式三中三，35.40.43.46.48，10组每组2） ======
        # 规则：玩法名称+空格/逗号+号码列表+金额
        fushi_forward_match = re.match(r'复[试式]三中三[，,]*\s+([\d.,，、\s]+)[，,]*([\d一二三四五六七八九十百千元米块]+|共[\d一二三四五六七八九十]+组每组[\d一二三四五六七八九十百千元米块]+|[\d]+组每组[\d一二三四五六七八九十百千元米块]+)?', line)
        if fushi_forward_match:
            from itertools import combinations
            nums_str = fushi_forward_match.group(1)
            amount_str = fushi_forward_match.group(2) if fushi_forward_match.group(2) else ''
            amount = parse_amount(amount_str) if amount_str else 0
            if amount <= 0:
                amount_match = re.search(r'(\d+)(?:组每组)?([\d一二三四五六七八九十百千元米块]+)', line)
                if amount_match:
                    amount = parse_amount(amount_match.group(2)) if amount_match.group(2) else parse_amount(amount_match.group(1))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for combo in combinations(valid_nums, 3):
                    for num in combo:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式12c：新澳+三中三格式（新澳三中三，25.33.14...9组每组10） ======
        xin_ao_szs_match = re.match(r'新[奥澳]\s*三中三[，,]\s*([\d.,，、\s]+?)(?:\s+(\d+组每组[\d一二三四五六七八九十百千元米块]+))?$', line)
        if xin_ao_szs_match:
            from itertools import combinations
            nums_str = xin_ao_szs_match.group(1)
            amount = 0
            gezu_match = re.search(r'(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', line)
            if gezu_match:
                amount = parse_amount(gezu_match.group(2))
            groups = re.split(r'，', nums_str)
            all_valid_nums = []
            for group in groups:
                nums = re.findall(r'(\d{1,2})', group)
                valid_nums = []
                for n in nums:
                    if 1 <= int(n) <= 49:
                        valid_nums.append(str(int(n)).zfill(2))
                    else:
                        errors.append(f'号码{n}不在01-49范围内，已忽略')
                if valid_nums:
                    all_valid_nums.extend(valid_nums)
            all_valid_nums = list(set(all_valid_nums))
            if all_valid_nums and amount > 0:
                for combo in combinations(all_valid_nums, 3):
                    for num in combo:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式12d：新奥+连肖格式（新奥5连肖 / 新奥，4连肖） ======
        xin_ao_lianxiao_match = re.match(r'新[奥澳][，,]*\s*([\d一二三四五六七八九十]+)连肖', line)
        if xin_ao_lianxiao_match:
            cn_num = xin_ao_lianxiao_match.group(1)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            if cn_num.isdigit():
                num = int(cn_num)
            else:
                num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                add_bet(results, '', 0, '特码', play_name, '', line_num)
            continue
        
        # ====== 格式12e：新奥+复试三中三（新奥 复试三中三） ======
        xin_ao_fushi_szs_match = re.match(r'新[奥澳]\s+复[试式]三中三', line)
        if xin_ao_fushi_szs_match:
            add_bet(results, '', 0, '平码', '平码三中三', '', line_num)
            continue
        
        # ====== 格式13：二中二（二中二09/35=20米） ======
        erzhonger_match = re.match(r'二中二([\d/,，、\s]+)[=:：]*([\d一二三四五六七八九十百千元米块]+)', line)
        if erzhonger_match:
            nums_str = erzhonger_match.group(1)
            amount = parse_amount(erzhonger_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '平码', '玩法': '平码二中二',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式14：特码17投注100元 ======
        tema_match = re.match(r'特码(\d{1,2})投注([\d一二三四五六七八九十百千]+)元', line)
        if tema_match:
            num = tema_match.group(1)
            amount = cn_to_num(tema_match.group(2))
            num_str = str(int(num)).zfill(2)
            if 1 <= int(num) <= 49:
                results.append({
                    '号码': num_str, '金额': amount,
                    '类型': '特码', '玩法': '特码',
                    '投注对象': num_str, '行号': line_num
                })
            else:
                errors.append(f'号码{num}不在01-49范围内，已忽略')
            continue
        
        # ====== 格式15：平码05,17投注20元 ======
        pingma_match = re.match(r'平码([\d,，]+)投注([\d一二三四五六七八九十百千]+)元', line)
        if pingma_match:
            nums_str = pingma_match.group(1)
            amount = cn_to_num(pingma_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '平码', '玩法': '平码',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式16：特肖虎投注50元 ======
        teshou_match = re.match(r'特肖([' + zodiac_chars + r'])投注([\d一二三四五六七八九十百千]+)元', line)
        if teshou_match:
            zodiac = teshou_match.group(1)
            amount = cn_to_num(teshou_match.group(2))
            # 特肖投注不展开成号码，只作为1笔记录
            results.append({
                '号码': zodiac,         # 直接存储生肖名称
                '金额': amount,        # 投注金额不变（不乘4倍）
                '类型': '特码',        # 特码类型
                '玩法': '特肖',        # 特肖玩法
                '投注对象': zodiac,     # 投注对象是生肖
                '行号': line_num       # 原始行号
            })
            continue
        
        # ====== 格式17：01/02/03数各20 ======
        all_num_match = re.match(r'^([\d/，,]+)数各([\d一二三四五六七八九十百千元米块]+)$', line)
        if all_num_match:
            nums_str = all_num_match.group(1)
            amount = parse_amount(all_num_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '特码', '玩法': '特码',
                        '投注对象': num, '行号': line_num
                    })
            continue
        
        # ====== 格式18：17/100 或 05,17/20 ======
        short_match = re.match(r'^([\d/,，]+)/([\d一二三四五六七八九十百千元米块]+)$', line)
        if short_match:
            nums_str = short_match.group(1)
            amount = parse_amount(short_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    results.append({
                        '号码': num, '金额': amount,
                        '类型': '特码', '玩法': '特码',
                        '投注对象': num, '行号': line_num
                    })
            continue

        # ====== 格式19：一肖虎投注50元（一肖看全部7个号码） ======
        yixiao_match = re.match(r'一肖([' + zodiac_chars + r'])投注([\d一二三四五六七八九十百千]+)元', line)
        if yixiao_match:
            zodiac = yixiao_match.group(1)
            amount = cn_to_num(yixiao_match.group(2))
            results.append({
                '号码': zodiac, '金额': amount,
                '类型': '特码', '玩法': '一肖',
                '投注对象': zodiac, '行号': line_num
            })
            continue

        # ====== 格式20：1尾投注50元 或 尾数1投注50元 ======
        weishu_match = re.match(r'(?:尾数)?(\d)尾投注([\d一二三四五六七八九十百千]+)元', line)
        if weishu_match:
            tail = weishu_match.group(1)
            amount = cn_to_num(weishu_match.group(2))
            results.append({
                '号码': tail + '尾', '金额': amount,
                '类型': '特码', '玩法': '尾数',
                '投注对象': tail + '尾', '行号': line_num
            })
            continue

        # ====== 格式21：五不中01,02,03,04,05投注50元（支持五至十二不中） ======
        buzhong_match = re.match(r'([五六七八九十十一十二])不中([\d,，、\s]+)投注([\d一二三四五六七八九十百千]+)元', line)
        if buzhong_match:
            cn_num = buzhong_match.group(1)
            nums_str = buzhong_match.group(2)
            amount = cn_to_num(buzhong_match.group(3))
            cn_to_num_map = {'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}
            play_name = f'{cn_num}不中'
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            results.append({
                '号码': ','.join(valid_nums), '金额': amount,
                '类型': '平码', '玩法': play_name,
                '投注对象': ','.join(valid_nums), '行号': line_num
            })
            continue
        
        # ====== 格式21b：号码列表X不中金额（02.03.06十二不中300米） ======
        # 规则：X不中格式，投注金额算1笔，不展开
        buzhong2_match = re.match(r'([\d.,，、\s]+?)(十二|十一|[五六七八九十])不中([\d一二三四五六七八九十百千元米块]+)', line)
        if buzhong2_match:
            nums_str = buzhong2_match.group(1)
            cn_num = buzhong2_match.group(2)
            amount_str = buzhong2_match.group(3)
            amount = parse_amount(amount_str)
            play_name = f'{cn_num}不中'
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            # X不中格式：算1笔，不展开
            results.append({
                '号码': ','.join(valid_nums), '金额': amount,
                '类型': '平码', '玩法': play_name,
                '投注对象': ','.join(valid_nums), '行号': line_num
            })
            continue
        
        # ====== 格式21c：平特X尾（平特1尾2000） ======
        # 规则：平特X尾格式，算1笔，不展开
        pingte_wei_match = re.match(r'平特(\d)尾([\d一二三四五六七八九十百千元米块]+)', line)
        if pingte_wei_match:
            tail = pingte_wei_match.group(1)
            amount = parse_amount(pingte_wei_match.group(2))
            results.append({
                '号码': tail + '尾', '金额': amount,
                '类型': '平码', '玩法': '平特尾数',
                '投注对象': tail + '尾', '行号': line_num
            })
            continue
        
        # ====== 格式21d：号码/金额格式（22/30米） ======
        # 规则：号码/金额，算1笔，不展开
        slash_match = re.match(r'(\d{1,2})/([\d一二三四五六七八九十百千元米块]+)', line)
        if slash_match:
            num = slash_match.group(1)
            amount = parse_amount(slash_match.group(2))
            num_str = str(int(num)).zfill(2)
            if 1 <= int(num) <= 49:
                add_bet(results, num_str, amount, bet_type, '特码' if not is_pingma else '平码', num_str, line_num)
            else:
                errors.append(f'号码{num}不在01-49范围内，已忽略')
            continue
        
        # ====== 格式21f：括号组连肖（【牛蛇狗】【猪兔羊】【龙狗鸡】每组各20米） ======
        # 规则：每个【生肖组】算1笔，共X组，每组金额相同
        # 支持合并后的格式：【牛蛇狗】【猪兔羊】 每组各 20米 三连肖
        bracket_lianxiao_match = re.match(r'([【\[（(][' + zodiac_chars + r']+[】\]）)]+)+\s*(每组各|每组|各)?\s*([\d一二三四五六七八九十百千元米块]+)\s*(三连肖)?', line)
        if bracket_lianxiao_match:
            bracket_groups = re.findall(r'[【\[（(]([' + zodiac_chars + r']+)[】\]）)]', line)
            amount_str = bracket_lianxiao_match.group(3)
            amount = parse_amount(amount_str)
            for group in bracket_groups:
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', group)
                if zodiacs and amount > 0:
                    play_name = f'{len(zodiacs)}连肖'
                    add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21f2：括号组连肖 - 更宽松的格式 ======
        # 支持：【牛蛇狗】【猪兔羊】【龙狗鸡】 【鼠牛兔】【虎猪狗】【猴鸡羊】 每组各 20米
        bracket_lianxiao_match2 = re.match(r'((?:【[' + zodiac_chars + r']+】\s*)+)', line)
        if bracket_lianxiao_match2:
            bracket_groups = re.findall(r'【([' + zodiac_chars + r']+)】', line)
            # 查找金额
            amount_match = re.search(r'(每组各|每组|各)\s*([\d一二三四五六七八九十百千元米块]+)', line)
            if amount_match:
                amount = parse_amount(amount_match.group(2))
            else:
                amount = 0
            for group in bracket_groups:
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', group)
                if zodiacs and amount > 0:
                    play_name = f'{len(zodiacs)}连肖'
                    add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21g：平特一肖（平特一肖兔2000） ======
        # 规则：平特一肖+生肖+金额，算1笔，不展开
        pingte_yixiao_match = re.match(r'平特一肖([' + zodiac_chars + r'])([\d一二三四五六七八九十百千元米块]+)', line)
        if pingte_yixiao_match:
            zodiac = pingte_yixiao_match.group(1)
            amount = parse_amount(pingte_yixiao_match.group(2))
            results.append({
                '号码': zodiac, '金额': amount,
                '类型': '平码', '玩法': '平特一肖',
                '投注对象': zodiac, '行号': line_num
            })
            continue
        
        # ====== 格式21h：平特三肖（平特三肖: 羊鸡狗 猴蛇羊 虎马兔 兔羊猴 蛇猴鸡每组10米） ======
        # 规则：每个生肖组合算1笔
        pingte_sanxiao_match = re.match(r'平特三肖[:：]\s*(.+)\s*每组([\d一二三四五六七八九十百千元米块]+)', line)
        if pingte_sanxiao_match:
            groups_str = pingte_sanxiao_match.group(1)
            amount = parse_amount(pingte_sanxiao_match.group(2))
            # 按空格或标点分隔各个生肖组合
            groups = re.split(r'[\s，,、]+', groups_str)
            for group in groups:
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', group)
                if zodiacs and amount > 0:
                    add_bet(results, ','.join(zodiacs), amount, '平码', '平特三肖', ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21i：头/尾各号格式（4头各号10米、2.3尾各号10米） ======
        # 规则：头/尾投注，算1笔，不展开
        touwei_match = re.match(r'([\d.，,、]+)(头|尾)各号([\d一二三四五六七八九十百千元米块]+)', line)
        if touwei_match:
            targets = touwei_match.group(1)
            tw_type = touwei_match.group(2)
            amount = parse_amount(touwei_match.group(3))
            targets = targets.replace('.', '').replace('，', '').replace(',', '')
            results.append({
                '号码': targets + tw_type, '金额': amount,
                '类型': '特码', '玩法': f'{tw_type}数',
                '投注对象': targets + tw_type, '行号': line_num
            })
            continue
        
        # ====== 格式21j：连肖简写格式（三连，兔龙牛，30 / 四连，羊龙猪牛，30） ======
        # 规则：数字连+逗号+生肖+逗号+金额，算1笔
        lianxiao_short_match = re.match(r'([\d一二三四五六七八九十]+)连[，,]\s*([' + zodiac_chars + r']+)[，,]\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if lianxiao_short_match:
            cn_num = lianxiao_short_match.group(1)
            zodiacs_str = lianxiao_short_match.group(2)
            amount_str = lianxiao_short_match.group(3)
            amount = parse_amount(amount_str)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            if cn_num.isdigit():
                num = int(cn_num)
            else:
                num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
                if zodiacs:
                    add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21k：复式三中三带括号格式（（03-07-19-30-40）10组各组1米） ======
        # 规则：括号内号码列表，共X组每组Y米
        fushi_paren_match = re.match(r'[（(]([\d.,，、\-/]+)[)）]\s*(?:共)?(\d+)组各组([\d一二三四五六七八九十百千元米块]+)', line)
        if fushi_paren_match:
            from itertools import combinations
            nums_str = fushi_paren_match.group(1)
            groups_count = int(fushi_paren_match.group(2))
            amount = parse_amount(fushi_paren_match.group(3))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for combo in combinations(valid_nums, 3):
                    for num in combo:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21l：三中三带括号格式（（06-46-17，28-38-40，40-38-19）各组10米） ======
        # 规则：括号内多组三中三号码，各组Y米
        szs_paren_match = re.match(r'[（(]([\d.,，、\-/\s]+)[)）]\s*(?:各组|每组)([\d一二三四五六七八九十百千元米块]+)', line)
        if szs_paren_match:
            nums_str = szs_paren_match.group(1)
            amount = parse_amount(szs_paren_match.group(2))
            groups = re.split(r'，', nums_str)
            for group in groups:
                nums = re.findall(r'(\d{1,2})', group)
                valid_nums = []
                for n in nums:
                    if 1 <= int(n) <= 49:
                        valid_nums.append(str(int(n)).zfill(2))
                    else:
                        errors.append(f'号码{n}不在01-49范围内，已忽略')
                if valid_nums and amount > 0:
                    for num in valid_nums:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21m：各数格式（老鼠各数5 / 07各数5） ======
        # 规则：各数 = 展开成所有对应号码，每个号码算1笔
        geshu_match = re.match(r'([' + zodiac_chars + r']|\d{1,2})各数([\d一二三四五六七八九十百千元米块]+)', line)
        if geshu_match:
            target = geshu_match.group(1)
            amount = parse_amount(geshu_match.group(2))
            if target in ZODIAC_NUMBERS:
                # 生肖各数：展开成所有对应号码
                results.extend(expand_zodiac_to_numbers(target, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            elif target.isdigit() and 1 <= int(target) <= 49:
                # 号码各数：直接记录
                num_str = str(int(target)).zfill(2)
                add_bet(results, num_str, amount, '特码', '特码', num_str, line_num)
            continue
        
        # ====== 格式21n：号码列表各X格式（35-10各五十 / 11-23-35-47各十） ======
        # 规则：号码列表+各+中文数字金额
        num_ge_cn_match = re.match(r'([\d.,，、\-/\s]+)各([一二三四五六七八九十百千]+)', line)
        if num_ge_cn_match and '三中三' not in line and '复试' not in line and '二中二' not in line and '不中' not in line:
            nums_str = num_ge_cn_match.group(1)
            amount_str = num_ge_cn_match.group(2)
            amount = cn_to_num(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, '特码', '特码', num, line_num)
            continue
        
        # ====== 格式21o：下X格式（15下1000） ======
        # 规则：号码下金额，算1笔
        xia_match = re.match(r'(\d{1,2})下([\d一二三四五六七八九十百千元米块]+)', line)
        if xia_match:
            num = xia_match.group(1)
            amount = parse_amount(xia_match.group(2))
            num_str = str(int(num)).zfill(2)
            if 1 <= int(num) <= 49:
                add_bet(results, num_str, amount, '特码', '特码', num_str, line_num)
            else:
                errors.append(f'号码{num}不在01-49范围内，已忽略')
            continue
        
        # ====== 格式21p：生肖每个号各格式（鸡每个号各100） ======
        # 规则：生肖+每个号各+金额，展开成所有对应号码
        sx_meigehao_match = re.match(r'([' + zodiac_chars + r']+)每个号各([\d一二三四五六七八九十百千元米块]+)', line)
        if sx_meigehao_match:
            zodiac_str = sx_meigehao_match.group(1)
            amount_str = sx_meigehao_match.group(2)
            amount = parse_amount(amount_str)
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            for z in zodiacs:
                results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            continue
        
        # ====== 格式21q：澳平特前缀（澳平特 虎狗各100） ======
        # 规则：澳平特+生肖+各+金额，平码，不展开
        aopingte_match = re.match(r'澳平特\s*([' + zodiac_chars + r'，,、\s]+)各([\d一二三四五六七八九十百千元米块]+)', line)
        if aopingte_match:
            zodiac_str = aopingte_match.group(1)
            amount = parse_amount(aopingte_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            for z in zodiacs:
                add_bet(results, z, amount, '平码', '平特一肖', z, line_num)
            continue
        
        # ====== 格式21r：三连+生肖+金额（三连 猴虎狗100） ======
        # 规则：连+生肖+金额，算1笔
        lian_short2_match = re.match(r'([一二三四五六七八九十]+)连\s*([' + zodiac_chars + r']+)([\d一二三四五六七八九十百千元米块]+)', line)
        if lian_short2_match:
            cn_num = lian_short2_match.group(1)
            zodiacs_str = lian_short2_match.group(2)
            amount_str = lian_short2_match.group(3)
            amount = parse_amount(amount_str)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
                if zodiacs:
                    add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21s：特号码买X元（特09买5元，03.05.07.01各2） ======
        # 规则：特+号码+买+金额，逗号分隔多个，支持"买X元"和"各X"格式
        te_mai_match = re.match(r'特([\d，,、\s]+)买([\d一二三四五六七八九十百千]+)元', line)
        if te_mai_match:
            nums_str = te_mai_match.group(1)
            amount = cn_to_num(te_mai_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, '特码', '特码', num, line_num)
            # 处理逗号后面的部分（如"，03.05.07.01各2"）
            matched_end = te_mai_match.end()
            remaining = line[matched_end:].strip()
            if remaining:
                remaining_results, remaining_errors = parse_bet_input(remaining)
                for r in remaining_results:
                    r['行号'] = line_num
                results.extend(remaining_results)
                errors.extend(remaining_errors)
            continue
        
        # ====== 格式21t：复式X连肖格式（复式5连肖 / 羊兔鸡牛龙蛇，6组每组5） ======
        # 规则：复式+数字+连肖，或者生肖组合+X组每组Y
        fushi_lianxiao_match = re.match(r'(?:复式)?([\d一二三四五六七八九十]+)连肖\s*([' + zodiac_chars + r']+)?(?:，)?([\d一二三四五六七八九十]+)?组每组([\d一二三四五六七八九十百千元米块]+)?', line)
        if fushi_lianxiao_match:
            cn_num = fushi_lianxiao_match.group(1)
            zodiacs_str = fushi_lianxiao_match.group(2)
            groups_count = fushi_lianxiao_match.group(3)
            amount_str = fushi_lianxiao_match.group(4)
            if zodiacs_str and amount_str:
                amount = parse_amount(amount_str)
                cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
                if cn_num.isdigit():
                    num = int(cn_num)
                else:
                    num = cn_to_num_map.get(cn_num, 0)
                if num > 0:
                    play_name = f'{num}连肖'
                    zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
                    if zodiacs:
                        # 复式连肖：每个组合算1笔
                        add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21u：X连肖+生肖+1组X（牛鸡鼠猴，1组20） ======
        lianxiao_1zu_match = re.match(r'([' + zodiac_chars + r']+)[，,]\s*1组([\d一二三四五六七八九十百千元米块]+)', line)
        if lianxiao_1zu_match:
            zodiacs_str = lianxiao_1zu_match.group(1)
            amount = parse_amount(lianxiao_1zu_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            if zodiacs and amount > 0:
                play_name = f'{len(zodiacs)}连肖'
                add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21v：三中三多组格式（25.33.14，19.38.41，36.30.02三中三） ======
        szs_multigroup_match = re.match(r'([\d.,，、\s]+)\s*三中三', line)
        if szs_multigroup_match:
            from itertools import combinations
            nums_str = szs_multigroup_match.group(1)
            # 查找金额（可能在行尾）
            amount_match = re.search(r'([\d一二三四五六七八九十]+)组每组([\d一二三四五六七八九十百千元米块]+)', line)
            if amount_match:
                amount = parse_amount(amount_match.group(2))
            else:
                amount_match2 = re.search(r'每组([\d一二三四五六七八九十百千元米块]+)', line)
                if amount_match2:
                    amount = parse_amount(amount_match2.group(1))
                else:
                    amount = 0
            if amount > 0:
                groups = re.split(r'，', nums_str)
                for group in groups:
                    nums = re.findall(r'(\d{1,2})', group)
                    valid_nums = []
                    for n in nums:
                        if 1 <= int(n) <= 49:
                            valid_nums.append(str(int(n)).zfill(2))
                        else:
                            errors.append(f'号码{n}不在01-49范围内，已忽略')
                    if valid_nums and len(valid_nums) >= 3:
                        for combo in combinations(valid_nums, 3):
                            for num in combo:
                                add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21w：号码三中三+中文金额（26.34.46三中三，十块） ======
        szs_cn_amount_match = re.match(r'([\d.,，、\s]+)三中三[，,]([\d一二三四五六七八九十百千元米块]+)', line)
        if szs_cn_amount_match:
            nums_str = szs_cn_amount_match.group(1)
            amount = parse_amount(szs_cn_amount_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21x：复试三中三各组X块共X组（07.26.35.38复试三中三各组五块共四组） ======
        fushi_szs_match = re.match(r'([\d.,，、\s]+)复[试式]三中三各组([\d一二三四五六七八九十百千元米块]+)共(\d+)组', line)
        if fushi_szs_match:
            from itertools import combinations
            nums_str = fushi_szs_match.group(1)
            amount = parse_amount(fushi_szs_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for combo in combinations(valid_nums, 3):
                    for num in combo:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21y：3🀄️3格式（牛鸡猪 3🀄️3下100） ======
        szs_emoji_match = re.match(r'([' + zodiac_chars + r']+)\s*3🀄️3(?:下)?([\d一二三四五六七八九十百千元米块]+)', line)
        if szs_emoji_match:
            zodiacs_str = szs_emoji_match.group(1)
            amount = parse_amount(szs_emoji_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            # 3🀄️3 = 三中三，展开成号码
            if zodiacs and amount > 0:
                all_nums = []
                for z in zodiacs:
                    all_nums.extend(ZODIAC_NUMBERS.get(z, []))
                all_nums = list(set(all_nums))
                for num in all_nums:
                    add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21z：澳特：多号码格式（200澳特：36=20米，19=10米，20、32、44、23各5米） ======
        aote_multi_match = re.match(r'澳特[:：]\s*(.+)$', line)
        if aote_multi_match:
            content = aote_multi_match.group(1)
            # 按逗号分隔
            parts = re.split(r'[，,]+', content)
            for part in parts:
                part = part.strip()
                if '=' in part:
                    num, amount_str = part.split('=', 1)
                    num = num.strip()
                    amount_str = amount_str.strip()
                    amount = parse_amount(amount_str)
                    if num.isdigit() and 1 <= int(num) <= 49:
                        num_str = str(int(num)).zfill(2)
                        add_bet(results, num_str, amount, '特码', '特码', num_str, line_num)
                elif '各' in part:
                    nums_str, amount_str = part.split('各', 1)
                    nums_str = nums_str.strip()
                    amount_str = amount_str.strip()
                    amount = parse_amount(amount_str)
                    nums = re.findall(r'(\d{1,2})', nums_str)
                    valid_nums = []
                    for n in nums:
                        if 1 <= int(n) <= 49:
                            valid_nums.append(str(int(n)).zfill(2))
                        else:
                            errors.append(f'号码{n}不在01-49范围内，已忽略')
                    valid_nums = list(set(valid_nums))
                    if valid_nums and amount > 0:
                        for num in valid_nums:
                            add_bet(results, num, amount, '特码', '特码', num, line_num)
            continue
        
        # ====== 格式21aa：连肖多组格式（5连肖 猪兔狗龙虎 鸡鼠虎狗龙 每组五块） ======
        # 规则：每行一个生肖组合，算1笔
        lianxiao_multi_match = re.match(r'([\d一二三四五六七八九十]+)连肖\s*([' + zodiac_chars + r']+)', line)
        if lianxiao_multi_match:
            cn_num = lianxiao_multi_match.group(1)
            zodiacs_str = lianxiao_multi_match.group(2)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            if cn_num.isdigit():
                num = int(cn_num)
            else:
                num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
                if zodiacs:
                    add_bet(results, ','.join(zodiacs), 0, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21ab：每组金额格式（每组五块 / 每组各 20米） ======
        # 规则：为上一行的连肖设置金额
        mezu_amount_match = re.match(r'(每组各|每组)\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if mezu_amount_match:
            amount = parse_amount(mezu_amount_match.group(2))
            # 查找上一行的结果，设置金额
            if results:
                # 找到最近的连肖记录
                for i in range(len(results)-1, -1, -1):
                    if '连肖' in results[i]['玩法'] and results[i]['金额'] == 0:
                        results[i]['金额'] = amount
                        break
            continue
        
        # ====== 格式21ac：特号码各中文金额（特11.22.33.44各五米） ======
        te_ge_cn_match = re.match(r'特([\d.,，、\s]+)各([一二三四五六七八九十百千]+)', line)
        if te_ge_cn_match:
            nums_str = te_ge_cn_match.group(1)
            amount_str = te_ge_cn_match.group(2)
            amount = cn_to_num(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, '特码', '特码', num, line_num)
            continue
        
        # ====== 格式21ad：复式三中三+共X组每组Y（02.11.12.15.21.35，共20组、每组10 复式三中三） ======
        fushi_szs_gezu_match = re.match(r'([\d.,，、\s]+)[，,]*共(\d+)组[、，,]*每组([\d一二三四五六七八九十百千元米块]+)\s*复[试式]三中三', line)
        if fushi_szs_gezu_match:
            from itertools import combinations
            nums_str = fushi_szs_gezu_match.group(1)
            amount = parse_amount(fushi_szs_gezu_match.group(3))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for combo in combinations(valid_nums, 3):
                    for num in combo:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21ae：生肖每个号+中文金额（猴每个号二十五） ======
        sx_meige_cn_match = re.match(r'([' + zodiac_chars + r']+)每个号([一二三四五六七八九十百千]+)', line)
        if sx_meige_cn_match:
            zodiac_str = sx_meige_cn_match.group(1)
            amount_str = sx_meige_cn_match.group(2)
            amount = cn_to_num(amount_str)
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            for z in zodiacs:
                results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            continue
        
        # ====== 格式21af：连肖简写多逗号格式（三连，，兔龙牛，30） ======
        lianxiao_double_comma_match = re.match(r'([\d一二三四五六七八九十]+)连[，,]+([' + zodiac_chars + r']+)[，,]\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if lianxiao_double_comma_match:
            cn_num = lianxiao_double_comma_match.group(1)
            zodiacs_str = lianxiao_double_comma_match.group(2)
            amount_str = lianxiao_double_comma_match.group(3)
            amount = parse_amount(amount_str)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            if cn_num.isdigit():
                num = int(cn_num)
            else:
                num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
                if zodiacs:
                    add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21ag：三中三多组+金额格式（9组每组10） ======
        szs_groups_match = re.match(r'(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', line)
        if szs_groups_match:
            groups_count = int(szs_groups_match.group(1))
            amount = parse_amount(szs_groups_match.group(2))
            if amount > 0:
                # 查找上一行的三中三记录，设置金额
                for i in range(len(results)-1, -1, -1):
                    if '三中三' in results[i]['玩法'] and results[i]['金额'] == 0:
                        results[i]['金额'] = amount
                        break
            continue
        
        # ====== 格式21ah：复式三中三+号码+共X组每组Y（36.16.38.31.17，10组每组2 复式三中三） ======
        fushi_szs_reverse_match = re.match(r'([\d.,，、\s]+)[，,]*(\d+)组每组([\d一二三四五六七八九十百千元米块]+)\s*复[试式]三中三', line)
        if fushi_szs_reverse_match:
            from itertools import combinations
            nums_str = fushi_szs_reverse_match.group(1)
            amount = parse_amount(fushi_szs_reverse_match.group(3))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for combo in combinations(valid_nums, 3):
                    for num in combo:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21ai：生肖组+X组每组Y（羊兔鸡牛龙蛇，6组每组5） ======
        sx_groups_match = re.match(r'([' + zodiac_chars + r']+)[，,]\s*(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', line)
        if sx_groups_match:
            zodiacs_str = sx_groups_match.group(1)
            amount = parse_amount(sx_groups_match.group(3))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            if zodiacs and amount > 0:
                play_name = f'{len(zodiacs)}连肖'
                add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21aj：生肖组+1组X（鸡虎猪鼠蛇    1组30） ======
        sx_1zu_match = re.match(r'([' + zodiac_chars + r']+)\s+1组([\d一二三四五六七八九十百千元米块]+)', line)
        if sx_1zu_match:
            zodiacs_str = sx_1zu_match.group(1)
            amount = parse_amount(sx_1zu_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            if zodiacs and amount > 0:
                play_name = f'{len(zodiacs)}连肖'
                add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue
        
        # ====== 格式21ak：特号码列表各X（特9，21，33，45，11，23，35，47各10） ======
        # 规则：特+号码列表+各+数字金额
        te_ge_num_match = re.match(r'特([\d，,、\s]+)各([\d一二三四五六七八九十百千元米块]+)', line)
        if te_ge_num_match:
            nums_str = te_ge_num_match.group(1)
            amount = parse_amount(te_ge_num_match.group(2))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, '特码', '特码', num, line_num)
            continue
        
        # ====== 格式21al：连肖多组格式（4连肖，狗鸡龙兔    鼠猪兔龙） ======
        # 规则：每行多个生肖组合，用空格分隔，每个组合算1笔
        lianxiao_multi_group_match = re.match(r'([\d一二三四五六七八九十]+)连肖[，,]\s*([' + zodiac_chars + r']+)\s+([' + zodiac_chars + r']+)', line)
        if lianxiao_multi_group_match:
            cn_num = lianxiao_multi_group_match.group(1)
            zodiacs_str1 = lianxiao_multi_group_match.group(2)
            zodiacs_str2 = lianxiao_multi_group_match.group(3)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            if cn_num.isdigit():
                num = int(cn_num)
            else:
                num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                zodiacs1 = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str1)
                zodiacs2 = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str2)
                if zodiacs1:
                    add_bet(results, ','.join(zodiacs1), 0, '特码', play_name, ','.join(zodiacs1), line_num)
                if zodiacs2:
                    add_bet(results, ','.join(zodiacs2), 0, '特码', play_name, ','.join(zodiacs2), line_num)
            continue
        
        # ====== 格式21am：三中三多组格式（25.33.14，19.38.41，36.30.02三中三） ======
        szs_multi_match = re.match(r'([\d.,，、\s]+)\s*三中三', line)
        if szs_multi_match and '复试' not in line and '复式' not in line:
            nums_str = szs_multi_match.group(1)
            # 提取金额
            amount = 0
            amount_match = re.search(r'(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', line)
            if amount_match:
                amount = parse_amount(amount_match.group(2))
            else:
                amount_match2 = re.search(r'每组([\d一二三四五六七八九十百千元米块]+)', line)
                if amount_match2:
                    amount = parse_amount(amount_match2.group(1))
            groups = re.split(r'，', nums_str)
            for group in groups:
                nums = re.findall(r'(\d{1,2})', group)
                valid_nums = []
                for n in nums:
                    if 1 <= int(n) <= 49:
                        valid_nums.append(str(int(n)).zfill(2))
                    else:
                        errors.append(f'号码{n}不在01-49范围内，已忽略')
                if valid_nums and len(valid_nums) >= 3 and amount > 0:
                    for num in valid_nums:
                        add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue
        
        # ====== 格式21an：新奥X连肖格式（新奥5连肖 / 新奥 5连肖） ======
        xin_ao_lianxiao_match = re.match(r'新[奥澳]\s*([\d一二三四五六七八九十]+)连肖', line)
        if xin_ao_lianxiao_match:
            cn_num = xin_ao_lianxiao_match.group(1)
            cn_to_num_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            if cn_num.isdigit():
                num = int(cn_num)
            else:
                num = cn_to_num_map.get(cn_num, 0)
            if num > 0:
                play_name = f'{num}连肖'
                add_bet(results, '', 0, '特码', play_name, '', line_num)
            continue
        
        # ====== 格式21ao：生肖组+逗号+1组X（猴龙鸡牛猪 ，1组10） ======
        sx_comma_1zu_match = re.match(r'([' + zodiac_chars + r']+)\s*[，,]\s*1组([\d一二三四五六七八九十百千元米块]+)', line)
        if sx_comma_1zu_match:
            zodiacs_str = sx_comma_1zu_match.group(1)
            amount = parse_amount(sx_comma_1zu_match.group(2))
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            if zodiacs and amount > 0:
                play_name = f'{len(zodiacs)}连肖'
                add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue

        # ====== 格式22：二连肖虎龙投注50元（支持二至五连肖） ======
        lianxiao_match = re.match(r'([二三四五])连肖([' + zodiac_chars + r']+)投注([\d一二三四五六七八九十百千]+)元', line)
        if lianxiao_match:
            cn_num = lianxiao_match.group(1)
            zodiacs_str = lianxiao_match.group(2)
            amount = cn_to_num(lianxiao_match.group(3))
            cn_to_num_map = {'二':2,'三':3,'四':4,'五':5}
            play_name = f'{cn_num}连肖'
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            results.append({
                '号码': ','.join(zodiacs), '金额': amount,
                '类型': '特码', '玩法': play_name,
                '投注对象': ','.join(zodiacs), '行号': line_num
            })
            continue

        # ====== 格式22b：中文数字连肖+生肖+各+金额（三连肖鼠牛虎各20 / 二连肖龙蛇各15） ======
        # 规则：n连肖 = n个生肖的组合投注，算1笔，金额为各后数字
        lianxiao_ge_match = re.match(r'([二三四五])连肖([' + zodiac_chars + r']+)各([\d一二三四五六七八九十百千元米块]+)', line)
        if lianxiao_ge_match:
            cn_num = lianxiao_ge_match.group(1)
            zodiacs_str = lianxiao_ge_match.group(2)
            amount_str = lianxiao_ge_match.group(3)
            amount = parse_amount(amount_str)
            play_name = f'{cn_num}连肖'
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            # 连肖是组合投注，n个生肖算1笔
            if zodiacs and amount > 0:
                add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue

        # ====== 格式23：二连尾1,2投注50元（支持二至七连尾） ======
        lianwei_match = re.match(r'([二三四五六七])连尾([\d,，、\s]+)投注([\d一二三四五六七八九十百千]+)元', line)
        if lianwei_match:
            cn_num = lianwei_match.group(1)
            tails_str = lianwei_match.group(2)
            amount = cn_to_num(lianwei_match.group(3))
            play_name = f'{cn_num}连尾'
            tails = re.findall(r'(\d)', tails_str)
            results.append({
                '号码': ','.join([t+'尾' for t in tails]), '金额': amount,
                '类型': '特码', '玩法': play_name,
                '投注对象': ','.join(tails), '行号': line_num
            })
            continue

        # ====== 格式24：三中二06,07,08投注50元（组合玩法） ======
        zuhe_match = re.match(r'(三中二|三全中|二全中|二中特|特中)([\d,，、\s]+)投注([\d一二三四五六七八九十百千]+)元', line)
        if zuhe_match:
            play_name = zuhe_match.group(1)
            nums_str = zuhe_match.group(2)
            amount = cn_to_num(zuhe_match.group(3))
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            results.append({
                '号码': ','.join(valid_nums), '金额': amount,
                '类型': '平码', '玩法': play_name,
                '投注对象': ','.join(valid_nums), '行号': line_num
            })
            continue

        # ====== 格式25：生肖对碰虎龙投注50元（展开成16笔） ======
        sxduipeng_match = re.match(r'生肖对碰([' + zodiac_chars + r']{2})投注([\d一二三四五六七八九十百千]+)元', line)
        if sxduipeng_match:
            zodiacs = sxduipeng_match.group(1)
            amount = cn_to_num(sxduipeng_match.group(2))
            z1, z2 = zodiacs[0], zodiacs[1]
            nums1 = ZODIAC_NUMBERS.get(z1, [])
            nums2 = ZODIAC_NUMBERS.get(z2, [])
            for n1 in nums1:
                for n2 in nums2:
                    results.append({
                        '号码': f'{n1}+{n2}', '金额': amount,
                        '类型': '平码', '玩法': '生肖对碰',
                        '投注对象': f'{z1}+{z2}', '行号': line_num
                    })
            continue

        # ====== 格式26：尾数对碰1,2投注50元（展开成25笔） ======
        wsduipeng_match = re.match(r'尾数对碰(\d),(\d)投注([\d一二三四五六七八九十百千]+)元', line)
        if wsduipeng_match:
            t1, t2 = wsduipeng_match.group(1), wsduipeng_match.group(2)
            amount = cn_to_num(wsduipeng_match.group(3))
            nums1 = TAIL_NUMBERS.get(t1, [])
            nums2 = TAIL_NUMBERS.get(t2, [])
            for n1 in nums1:
                for n2 in nums2:
                    results.append({
                        '号码': f'{n1}+{n2}', '金额': amount,
                        '类型': '平码', '玩法': '尾数对碰',
                        '投注对象': f'{t1}尾+{t2}尾', '行号': line_num
                    })
            continue

        # ====== 格式27：生肖+各号/每号各/每号/各数+金额（猴虎狗鸡蛇牛各号30米 / 龙鸡每号各5） ======
        # 关键规则：各号/每号各/每号/各数 = 展开成所有对应号码，每个号码算1笔
        # 支持同一行空格分隔的多段投注（如"猴虎狗鸡蛇牛各号30米 兔鼠各15米"）
        sx_gehao_match = re.match(r'([' + zodiac_chars + r'][，,、\s]*)*[' + zodiac_chars + r']+[\s,，、]*(各号|每号各|每号|各数|各)([\d一二三四五六七八九十百千元米块]+)', line)
        if sx_gehao_match:
            # 提取生肖部分（关键词之前）
            keyword = sx_gehao_match.group(2)
            idx = line.index(keyword)
            zodiac_str = line[:idx]
            amount_str = sx_gehao_match.group(3)
            amount = parse_amount(amount_str)
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiac_str)
            # 各号/每号各/每号/各数/各 → 展开成所有对应号码，每个号码算1笔
            for z in zodiacs:
                results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
            # 检查是否有剩余部分（空格分隔的另一段投注，如"兔鼠各15米"）
            matched_end = sx_gehao_match.end()
            remaining = line[matched_end:].strip()
            if remaining:
                remaining_results, remaining_errors = parse_bet_input(remaining)
                for r in remaining_results:
                    r['行号'] = line_num
                results.extend(remaining_results)
                errors.extend(remaining_errors)
            continue

        # ====== 格式28：号码列表+各号/各/每+金额（25.10.37.29.22.44.特各5米） ======
        # 支持 34.38.39.10.15.14.各5、22353325174826每个5米、15下1000、6.9.11各号5
        # 支持 01/02/03数各20（"数"是分隔符，等同于"各"）
        # 注意：排除包含"三中三"/"复试"的行，避免错误匹配（应由格式31/32处理）
        # 先用/分隔的号码格式（如01/02/03数各20）
        slash_num_match = re.match(r'([\d/]+)数[各号每]*\s*([\d一二三四五六七八九十百千元米块]+)', line)
        if slash_num_match and '三中三' not in line and '复试' not in line and '复试' not in line and '二中二' not in line:
            nums_str = slash_num_match.group(1)
            amount_str = slash_num_match.group(2)
            amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            is_tema = '特' in line
            play_name = '特码' if (is_tema or not is_pingma) else '平码'
            bt = '特码' if (is_tema or not is_pingma) else '平码'
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, bt, play_name, num, line_num)
            continue

        num_list_match = re.match(r'([\d\s.,，、]+)(特|平码)?(各号|每号|各数|各|每|每个|每组|下)?([\d一二三四五六七八九十百千元米块]+)', line)
        if num_list_match and not line.startswith(('特', '平', '一肖', '尾数', '五不中', '六不中', '七不中', '八不中', '九不中', '十不中', '生肖对碰', '尾数对碰', '三中', '二全', '二中', '特中', '复式', '复试')) and '三中三' not in line and '复试' not in line and '复试' not in line and '二中二' not in line and '/' not in line and '不中' not in line:
            nums_str = num_list_match.group(1)
            nums = re.findall(r'(\d{1,2})', nums_str)
            amount_str = num_list_match.group(4)
            amount = parse_amount(amount_str)
            # 判断特码标注
            is_tema = '特' in line
            play_name = '特码' if (is_tema or not is_pingma) else '平码'
            bt = '特码' if (is_tema or not is_pingma) else '平码'
            valid_nums = []
            for n in nums:
                if 1 <= int(n) <= 49:
                    valid_nums.append(str(int(n)).zfill(2))
                else:
                    errors.append(f'号码{n}不在01-49范围内，已忽略')
            valid_nums = list(set(valid_nums))
            if valid_nums and amount > 0:
                for num in valid_nums:
                    add_bet(results, num, amount, bt, play_name, num, line_num)
            continue

        # ====== 格式29：特码：08,17,26,35,44每个号五块 ======
        tema_list_match = re.match(r'特码[:：]\s*([\d,，、\s]+)(每个号|每个|各)?([\d一二三四五六七八九十百千元米块]+)', line)
        if tema_list_match:
            nums_str = tema_list_match.group(1)
            amount_str = tema_list_match.group(3) if tema_list_match.group(3) else tema_list_match.group(2)
            amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            for num in valid_nums:
                add_bet(results, num, amount, '特码', '特码', num, line_num)
            continue

        # ====== 格式30：特（22，44）各30米 ======
        te_paren_match = re.match(r'特[（(]([\d,，、\s]+)[)）](各|每个)?([\d一二三四五六七八九十百千元米块]+)', line)
        if te_paren_match:
            nums_str = te_paren_match.group(1)
            amount_str = te_paren_match.group(3)
            amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            for num in valid_nums:
                add_bet(results, num, amount, '特码', '特码', num, line_num)
            continue

        # ====== 格式31：三中三（07.22.39.三中三10米） ======
        # 支持 3🀄️3、三中三
        # 规则：n个号码选3个的组合 = C(n,3)组，每组展开成3个号码，每个号码1笔
        szs_match = re.match(r'([\d\s.,，、]+)(三中三|3🀄️3|3中3)(各组)?([\d一二三四五六七八九十百千元米块]+)', line)
        if szs_match:
            from itertools import combinations
            nums_str = szs_match.group(1)
            amount_str = szs_match.group(4)
            amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            # 每个组合展开成3个号码，每个号码算1笔
            for combo in combinations(valid_nums, 3):
                for num in combo:
                    add_bet(results, num, amount, '平码', '平码三中三', num, line_num)
            continue

        # ====== 格式32：复试/复试三中三/二中二（11.22.33.44.复试三中三各3米） ======
        # 规则：n个号码选m个的组合 = C(n,m)组，每组展开成m个号码，每个号码1笔
        # 4个号码三中三 = C(4,3)=4组 × 3号 = 12笔，每笔3元 = 36元
        # 4个号码二中二 = C(4,2)=6组 × 2号 = 12笔，每笔3元 = 36元
        # 注意：必须放在格式28之前，否则格式28正则会错误匹配（44变04 bug）
        fushi_match = re.match(r'([\d\s.,，、]+)复[试式](三中三|二中二)(各|每组)?([\d一二三四五六七八九十百千元米块]+)', line)
        if fushi_match:
            from itertools import combinations
            nums_str = fushi_match.group(1)
            play_cn = fushi_match.group(2)
            amount_str = fushi_match.group(4)
            amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            if play_cn == '三中三':
                play_name = '平码三中三'
                combo_size = 3
            else:
                play_name = '平码二中二'
                combo_size = 2
            # 每个组合展开成combo_size个号码，每个号码算1笔
            for combo in combinations(valid_nums, combo_size):
                for num in combo:
                    add_bet(results, num, amount, '平码', play_name, num, line_num)
            continue

        # ====== 格式33：括号复试（03-07-19-30-40）10组各组1米 ======
        paren_fushi_match = re.match(r'[（(]([\d\-.,，、\s]+)[)）](\d+)组(各组)?([\d一二三四五六七八九十百千元米块]+)', line)
        if paren_fushi_match:
            nums_str = paren_fushi_match.group(1).replace('-', ',').replace('，', ',')
            groups = int(paren_fushi_match.group(2))
            amount_str = paren_fushi_match.group(4)
            amount = parse_amount(amount_str)
            nums = re.findall(r'(\d{1,2})', nums_str)
            valid_nums = [str(int(n)).zfill(2) for n in nums if 1 <= int(n) <= 49]
            for num in valid_nums:
                add_bet(results, num, amount * groups, '平码', '平码三中三', num, line_num)
            continue

        # ====== 格式34：连肖（三连肖【牛蛇狗】【猪兔羊】每组各20米） ======
        lianxiao_bracket_match = re.match(r'([二三四五])连肖(.+?)每组(各)?([\d一二三四五六七八九十百千元米块]+)', line)
        if lianxiao_bracket_match:
            cn_num = lianxiao_bracket_match.group(1)
            content = lianxiao_bracket_match.group(2)
            amount_str = lianxiao_bracket_match.group(4)
            amount = parse_amount(amount_str)
            cn_to_num_map = {'二':2,'三':3,'四':4,'五':5}
            m = cn_to_num_map.get(cn_num, 3)
            play_name = f'{cn_num}连肖'
            # 提取【】中的生肖组
            groups = re.findall(r'[【[]([' + zodiac_chars + r']+)[】\]]', content)
            if not groups:
                # 没有括号，直接提取生肖
                groups = [content]
            for g in groups:
                zodiacs = re.findall(r'([' + zodiac_chars + r'])', g)
                if len(zodiacs) >= m:
                    add_bet(results, ','.join(zodiacs), amount, '特码', play_name, ','.join(zodiacs), line_num)
            continue

        # ====== 格式35：新奥+数字连肖（新澳 5连肖 / 新奥5连肖 / 新奥，4连肖） ======
        # 规则：新奥+数字连肖，不展开，1组算1笔
        xin_ao_num_lianxiao_match = re.match(r'新[奥澳][，,]*\s*(\d)连肖(?:[，,、\s]+([' + zodiac_chars + r'\s，,]+))?', line)
        if xin_ao_num_lianxiao_match:
            num = int(xin_ao_num_lianxiao_match.group(1))
            zodiacs_str = xin_ao_num_lianxiao_match.group(2)
            all_zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str) if zodiacs_str else []
            amount = 0
            zu_match = re.search(r'([\d一二三四五六七八九十]+)组([\d一二三四五六七八九十百千元米块]+)', line)
            if zu_match:
                amount = parse_amount(zu_match.group(2))
            else:
                meizu_match = re.search(r'每组([\d一二三四五六七八九十百千元米块]+)', line)
                if meizu_match:
                    amount = parse_amount(meizu_match.group(1))
                else:
                    all_nums = re.findall(r'(\d+)', line)
                    amount = int(all_nums[1]) if len(all_nums) > 1 else 0
            if amount <= 0:
                add_bet(results, '', 0, '特码', f'{num}连肖', '', line_num)
            else:
                cn_to_num_map = {2:'二',3:'三',4:'四',5:'五'}
                play_name = f'{cn_to_num_map.get(num, str(num))}连肖'
                if zodiacs_str:
                    parts = re.split(r'[\s，,]+', zodiacs_str.strip())
                    groups = []
                    current_group = []
                    for part in parts:
                        zs = re.findall(r'([' + zodiac_chars + r'])', part)
                        current_group.extend(zs)
                        if len(current_group) >= num:
                            groups.append(current_group[:num])
                            current_group = []
                    if not groups and all_zodiacs:
                        groups = [all_zodiacs[:num]]
                    for g in groups:
                        if len(g) == num:
                            add_bet(results, ','.join(g), amount, '特码', play_name, ','.join(g), line_num)
                else:
                    add_bet(results, '', amount, '特码', play_name, '', line_num)
            continue
        
        # ====== 格式35b：数字连肖（5连肖猴龙鸡牛猪，1组10 / 4连肖，狗鸡龙兔 鼠猪兔龙，每组五块 / 3连肖，猴 龙 羊，一组200） ======
        # 规则：连肖不展开，1组算1笔
        num_lianxiao_match = re.match(r'(\d)连肖[，,、\s]*(.+)$', line)
        if num_lianxiao_match:
            num = int(num_lianxiao_match.group(1))
            content = num_lianxiao_match.group(2)
            all_zodiacs = re.findall(r'([' + zodiac_chars + r'])', content)
            # 提取金额：支持"1组10"、"一组200"、"10"、"十块"、"每组五块"等格式
            amount = 0
            zu_match = re.search(r'(?:1组|一组|[\d]+组)([\d一二三四五六七八九十百千元米块]+)', line)
            if zu_match:
                amount = parse_amount(zu_match.group(1))
            else:
                meizu_match = re.search(r'每组([\d一二三四五六七八九十百千元米块]+)', line)
                if meizu_match:
                    amount = parse_amount(meizu_match.group(1))
                else:
                    all_nums = re.findall(r'(\d+)', line)
                    amount = int(all_nums[1]) if len(all_nums) > 1 else 0
            if amount <= 0:
                errors.append(f'行{line_num} [{original_line}] 连肖投注未填写金额，已跳过')
                continue
            # 判断是否有多组（用空格或逗号分隔的多段生肖）
            cn_to_num_map = {2:'二',3:'三',4:'四',5:'五'}
            play_name = f'{cn_to_num_map.get(num, str(num))}连肖'
            # 按空格/逗号分隔成多组，每组取num个生肖
            parts = re.split(r'[\s，,]+', content.strip())
            groups = []
            current_group = []
            for part in parts:
                zs = re.findall(r'([' + zodiac_chars + r'])', part)
                current_group.extend(zs)
                if len(current_group) >= num:
                    groups.append(current_group[:num])
                    current_group = []
            if not groups and all_zodiacs:
                groups = [all_zodiacs[:num]]
            for g in groups:
                if len(g) == num:
                    add_bet(results, ','.join(g), amount, '特码', play_name, ','.join(g), line_num)
            continue

        # ====== 格式36：复式5连肖（复式5连肖 羊兔鸡牛龙蛇，6组每组5 / 复式5连肖 猴鼠兔蛇龙虎，6组每组5） ======
        fushi_lianxiao_match = re.match(r'复式(\d)连肖\s*([' + zodiac_chars + r']+)[，,]\s*(\d+)组每组([\d一二三四五六七八九十百千元米块]+)', line)
        if fushi_lianxiao_match:
            m = int(fushi_lianxiao_match.group(1))
            zodiacs_str = fushi_lianxiao_match.group(2)
            groups_count = int(fushi_lianxiao_match.group(3))
            amount_str = fushi_lianxiao_match.group(4)
            amount = parse_amount(amount_str)
            cn_to_num_map = {2:'二',3:'三',4:'四',5:'五'}
            play_name = f'{cn_to_num_map.get(m, str(m))}连肖'
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            if zodiacs and amount > 0:
                add_bet(results, ','.join(zodiacs), amount * groups_count, '特码', play_name, ','.join(zodiacs), line_num)
            continue

        # ====== 格式37：头数（4头各号10米 = 40-49每个号10元） ======
        tou_match = re.match(r'(\d)头(各号|号|各)?([\d一二三四五六七八九十百千元米块]+)', line)
        if tou_match:
            head = int(tou_match.group(1))
            amount_str = tou_match.group(3)
            amount = parse_amount(amount_str)
            # 头数对应的号码：4头 = 40-49
            for i in range(10):
                num = str(head * 10 + i).zfill(2)
                if 1 <= int(num) <= 49:
                    add_bet(results, num, amount, bet_type, '平码' if is_pingma else '特码', f'{head}头', line_num)
            continue

        # ====== 格式38：尾数（2.3尾各号10米，平特3尾4000块） ======
        # 支持多尾数
        wei_match = re.match(r'([\d.,，、\s]+)尾(各号|号|各)?([\d一二三四五六七八九十百千元米块]+)', line)
        if wei_match:
            tails_str = wei_match.group(1)
            amount_str = wei_match.group(3)
            amount = parse_amount(amount_str)
            tails = re.findall(r'(\d)', tails_str)
            is_pingte = '平特' in line
            for t in tails:
                if is_pingte:
                    # 平特尾数：作为1笔
                    add_bet(results, t + '尾', amount, '平码', '平特尾数', t + '尾', line_num)
                else:
                    # 尾数投注：展开成该尾数所有号码
                    for num in TAIL_NUMBERS.get(t, []):
                        add_bet(results, num, amount, bet_type, '平码' if is_pingma else '特码', t + '尾', line_num)
            continue

        # ====== 格式39：老鼠各数5，07各数5（混合投注） ======
        # 这种格式在一行中包含生肖和号码，用逗号分隔
        # 各号/各数 = 展开成所有对应号码
        if '各数' in line or '各号' in line:
            keyword = '各数' if '各数' in line else '各号'
            parts = line.split(',')
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # 查找各数/各号位置
                if keyword in part:
                    idx = part.index(keyword)
                    obj_str = part[:idx].strip()
                    amount_str = part[idx+len(keyword):].strip()
                    amount = parse_amount(amount_str)
                    # 判断是生肖还是号码
                    zodiacs = re.findall(r'([' + zodiac_chars + r'])', obj_str)
                    nums = re.findall(r'(\d{1,2})', obj_str)
                    if zodiacs:
                        # 生肖 → 展开成所有对应号码
                        for z in zodiacs:
                            results.extend(expand_zodiac_to_numbers(z, amount, bet_type, '特码' if not is_pingma else '平码', line_num))
                    elif nums:
                        for n in nums:
                            num_str = str(int(n)).zfill(2)
                            if 1 <= int(n) <= 49:
                                add_bet(results, num_str, amount, bet_type, '特码' if not is_pingma else '平码', num_str, line_num)
            continue

        # ====== 格式40：生肖对碰（多个生肖连续，如猴虎狗鸡蛇牛各号30米已在格式27处理） ======
        # 此格式作为兜底：纯生肖+金额
        pure_zodiac_match = re.match(r'^([' + zodiac_chars + r']{2,})([\d一二三四五六七八九十百千元米块]+)$', line)
        if pure_zodiac_match:
            zodiacs_str = pure_zodiac_match.group(1)
            amount_str = pure_zodiac_match.group(2)
            amount = parse_amount(amount_str)
            zodiacs = re.findall(r'([' + zodiac_chars + r'])', zodiacs_str)
            for z in zodiacs:
                add_bet(results, z, amount, bet_type, '特码' if not is_pingma else '平码', z, line_num)
            continue

        # ====== 兜底：所有格式都未匹配 ======
        errors.append(f'第{line_num}行格式无法识别，请检查：{original_line}')

    # 金额验证
    for r in results:
        if r['金额'] <= 0:
            errors.append(f'号码{r["号码"]}金额{r["金额"]}无效，已忽略')

    return results, errors

# ==================== 开奖号码解析 ====================

def parse_kaijiang(kaijiang_str):
    """解析开奖号码"""
    if not kaijiang_str:
        return [], '', '', []
    
    clean_str = kaijiang_str.replace('特码', '')
    numbers = re.findall(r'(\d{1,2})', clean_str)
    valid_nums = [str(int(n)).zfill(2) for n in numbers if 1 <= int(n) <= 49]
    
    if len(valid_nums) >= 7:
        pingma = valid_nums[:6]
        tema = valid_nums[6]
        tema_zodiac = NUMBER_TO_ZODIAC.get(tema, '')
        return pingma, tema, tema_zodiac, valid_nums
    elif len(valid_nums) >= 1:
        return [], valid_nums[0], NUMBER_TO_ZODIAC.get(valid_nums[0], ''), valid_nums
    return [], '', '', []

# ==================== 中奖判断 ====================

def calculate_results(all_bets, pingma_nums, tema_num):
    """
    计算中奖结果
    中奖判断基于7个开奖号码（6个正码+1个特码）
    派彩只派一次，不重复派彩
    """
    results = []
    tema_num_str = str(tema_num).zfill(2) if tema_num else ''
    tema_zodiac = NUMBER_TO_ZODIAC.get(tema_num_str, '')
    all_kj_nums = pingma_nums + ([tema_num_str] if tema_num_str else [])
    # 所有开奖号码对应的生肖集合
    all_kj_zodiacs = set(NUMBER_TO_ZODIAC.get(n, '') for n in all_kj_nums)
    # 所有开奖号码对应的尾数集合
    all_kj_tails = set(n[-1] for n in all_kj_nums)

    for bet in all_bets:
        is_win = False
        bonus = 0
        num = bet['号码']
        play_type = bet['玩法']
        amount = bet['金额']

        if play_type == '特码':
            # 特码：只看特码号码
            if num == tema_num_str:
                is_win = True
                bonus = amount * ODDS_TABLE['特码']

        elif play_type == '平码':
            # 平码：看6个正码
            if num in pingma_nums:
                is_win = True
                bonus = amount * ODDS_TABLE['平码']

        elif play_type == '特肖':
            # 特肖：只看特码的生肖
            bet_zodiac = num  # num就是生肖名称
            if bet_zodiac == tema_zodiac:
                is_win = True
                bonus = amount * ODDS_TABLE['特肖']

        elif play_type == '一肖':
            # 一肖：看全部7个号码，只要出现该生肖的任意一个号码即中奖，派彩一次
            bet_zodiac = num  # num就是生肖名称
            if bet_zodiac in all_kj_zodiacs:
                is_win = True
                bonus = amount * ODDS_TABLE['一肖']

        elif play_type == '尾数':
            # 尾数：看全部7个号码，只要出现该尾数的任意一个号码即中奖，派彩一次
            bet_tail = num[0]  # num格式如'1尾'，取尾数数字
            if bet_tail in all_kj_tails:
                is_win = True
                bonus = amount * ODDS_TABLE['尾数']

        elif play_type in ('平码三中三', '平码二中二', '平码三中二'):
            # 平码组合玩法
            if num in all_kj_nums:
                is_win = True
                bonus = amount * ODDS_TABLE.get(play_type, 0)

        elif play_type.endswith('不中'):
            # 自选不中：7个开奖号码中都没有出现这些号码即中奖
            bet_nums = num.split(',')
            # 49算输赢，不为和
            hit = any(n in all_kj_nums for n in bet_nums)
            if not hit:
                is_win = True
                bonus = amount * ODDS_TABLE.get(play_type, 0)

        elif play_type.endswith('连肖'):
            # 连肖：7个开奖号码中至少要中2个生肖才算中奖
            bet_zodiacs = num.split(',')
            hit_count = sum(1 for z in bet_zodiacs if z in all_kj_zodiacs)
            if hit_count >= 2:
                is_win = True
                bonus = amount * ODDS_TABLE.get(play_type, 0)

        elif play_type.endswith('连尾'):
            # 连尾：7个开奖号码中至少要中2个尾数才算中奖
            bet_tails = [t[0] for t in num.split(',')]  # 格式如'1尾,2尾'
            hit_count = sum(1 for t in bet_tails if t in all_kj_tails)
            if hit_count >= 2:
                is_win = True
                bonus = amount * ODDS_TABLE.get(play_type, 0)

        elif play_type == '三中二':
            # 三中二：3个号码中，有2个是开奖正码→中奖；3个都是正码→按中三赔付
            bet_nums = num.split(',')
            hit_count = sum(1 for n in bet_nums if n in pingma_nums)
            if hit_count == 2:
                is_win = True
                bonus = amount * ODDS_TABLE['三中二']
            elif hit_count == 3:
                is_win = True
                bonus = amount * ODDS_TABLE['三全中']

        elif play_type == '三全中':
            # 三全中：3个号码都是开奖正码→中奖
            bet_nums = num.split(',')
            hit_count = sum(1 for n in bet_nums if n in pingma_nums)
            if hit_count == 3:
                is_win = True
                bonus = amount * ODDS_TABLE['三全中']

        elif play_type == '二全中':
            # 二全中：2个号码都是开奖正码→中奖
            bet_nums = num.split(',')
            hit_count = sum(1 for n in bet_nums if n in pingma_nums)
            if hit_count == 2:
                is_win = True
                bonus = amount * ODDS_TABLE['二全中']

        elif play_type == '二中特':
            # 二中特：2个号码都是正码→中二；1个正码+1个特码→中特
            bet_nums = num.split(',')
            pingma_hit = sum(1 for n in bet_nums if n in pingma_nums)
            tema_hit = sum(1 for n in bet_nums if n == tema_num_str)
            if pingma_hit == 2:
                is_win = True
                bonus = amount * ODDS_TABLE['二中特']
            elif pingma_hit == 1 and tema_hit == 1:
                is_win = True
                bonus = amount * ODDS_TABLE['特中']

        elif play_type == '特中':
            # 特中：1个正码+1个特码→中奖
            bet_nums = num.split(',')
            pingma_hit = sum(1 for n in bet_nums if n in pingma_nums)
            tema_hit = sum(1 for n in bet_nums if n == tema_num_str)
            if pingma_hit == 1 and tema_hit == 1:
                is_win = True
                bonus = amount * ODDS_TABLE['特中']

        elif play_type == '生肖对碰':
            # 生肖对碰：组合中的两个号码都出现在开奖正码中
            bet_nums = num.split('+')
            if all(n in pingma_nums for n in bet_nums):
                is_win = True
                bonus = amount * 6  # 生肖对碰按平码赔率

        elif play_type == '尾数对碰':
            # 尾数对碰：组合中的两个号码都出现在开奖正码中
            bet_nums = num.split('+')
            if all(n in pingma_nums for n in bet_nums):
                is_win = True
                bonus = amount * 6  # 尾数对碰按平码赔率

        elif '平特' in play_type:
            bet_zodiac = NUMBER_TO_ZODIAC.get(num, '')
            if bet_zodiac == tema_zodiac:
                is_win = True
                bonus = amount * 2

        results.append({
            **bet,
            '是否中奖': '✅' if is_win else '❌',
            '奖金': bonus
        })

    return results

# ==================== 数据持久化函数 ====================

def save_to_local_storage():
    """保存数据到本地存储"""
    import json
    data = {
        'all_bets': st.session_state.get('all_bets', []),
        'bet_history': st.session_state.get('bet_history', []),
        'kaijiang_input': st.session_state.get('kaijiang_input', ''),
        'save_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    st.session_state['saved_data'] = data
    st.success('✅ 数据已保存到本地存储')

def load_from_local_storage():
    """从本地存储加载数据"""
    if 'saved_data' in st.session_state:
        data = st.session_state['saved_data']
        st.session_state['all_bets'] = data.get('all_bets', [])
        st.session_state['bet_history'] = data.get('bet_history', [])
        st.session_state['kaijiang_input'] = data.get('kaijiang_input', '')
        st.success(f'✅ 已加载上次保存的数据（保存时间：{data.get("save_time", "")}）')

def export_to_excel(all_bets, has_kaijiang, pingma_nums, tema_num):
    """导出数据到Excel"""
    if not all_bets:
        st.warning('⚠️ 没有数据可导出')
        return
    
    qihao = st.session_state.get('qihao', '')
    filename = f'六合彩统计_{qihao if qihao else datetime.now().strftime("%Y%m%d")}.xlsx'
    
    if has_kaijiang:
        results = calculate_results(all_bets, pingma_nums, tema_num)
        df1 = pd.DataFrame(results)
        df1 = df1[['号码', '类型', '玩法', '金额', '是否中奖', '奖金']]
    else:
        df1 = pd.DataFrame(all_bets)
        df1 = df1[['号码', '类型', '玩法', '金额']]
    
    num_summary = {}
    for i in range(1, 50):
        num_str = str(i).zfill(2)
        num_summary[num_str] = {'总投注额': 0, '总中奖次数': 0, '类型': '号码', '生肖': NUMBER_TO_ZODIAC.get(num_str, '')}
    
    for bet in all_bets:
        num = bet['号码']
        if num in num_summary:
            num_summary[num]['总投注额'] += bet['金额']
    
    if has_kaijiang:
        tema_num_str = str(tema_num).zfill(2)
        for num_str in num_summary:
            if num_str == tema_num_str or num_str in pingma_nums:
                num_summary[num_str]['总中奖次数'] += 1
    
    df2 = pd.DataFrame.from_dict(num_summary, orient='index').reset_index()
    df2.columns = ['号码', '总投注额', '总中奖次数', '类型', '生肖']
    df2 = df2[df2['总投注额'] > 0]
    
    # 使用内存流生成Excel，兼容云端部署
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df1.to_excel(writer, sheet_name='投注明细', index=False)
        df2.to_excel(writer, sheet_name='号码汇总', index=False)
    output.seek(0)
    
    st.download_button(
        label='📥 下载Excel文件',
        data=output,
        file_name=filename,
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    st.success(f'✅ Excel文件已生成：{filename}')

def generate_report(all_bets, has_kaijiang, pingma_nums, tema_num, tema_zodiac):
    """生成结算报告"""
    if not all_bets:
        st.warning('⚠️ 没有数据可生成报告')
        return
    
    qihao = st.session_state.get('qihao', '')
    kaijiang_input = st.session_state.get('kaijiang_input', '')
    
    report = f"""🎯 六合彩结算报告
📅 期号：{qihao if qihao else '未填写'}
⏰ 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    if has_kaijiang:
        report += f"""
🎲 开奖号码：{kaijiang_input}
平码：{', '.join(pingma_nums)}
特码：{tema_num} ({tema_zodiac}肖)
"""
    
    total_amount = sum(b['金额'] for b in all_bets)
    total_count = len(all_bets)
    total_unique = len(set(b['号码'] for b in all_bets))
    total_rows = len(set(b.get('行号', i) for i, b in enumerate(all_bets)))
    total_bonus = 0
    
    report += f"""
📊 统计概览
─────────────
💰 总投注额：¥{total_amount:,}
📝 总笔数（号码数）：{total_unique}笔
📝 总记录数：{total_count}条
📝 总行数：{total_rows}行
"""
    
    if has_kaijiang:
        results = calculate_results(all_bets, pingma_nums, tema_num)
        total_bonus = sum(r['奖金'] for r in results)
        report += f"""🎁 总奖金：¥{total_bonus:,}
📈 总盈亏：¥{total_bonus - total_amount:,} ({'盈利' if total_bonus >= total_amount else '亏损'})
"""
    
    report += f"""
📋 投注明细
─────────────
"""
    
    if has_kaijiang:
        for i, r in enumerate(results, 1):
            report += f"{i}. 号码{r['号码']} | {r['类型']} | {r['玩法']} | 投注¥{r['金额']} | {r['是否中奖']} | 奖金¥{r['奖金']}\n"
    else:
        for i, b in enumerate(all_bets, 1):
            report += f"{i}. 号码{b['号码']} | {b['类型']} | {b['玩法']} | 投注¥{b['金额']}\n"
    
    st.text_area('结算报告', value=report, height=300, key='report_area')
    
    copy_js = """
    <script>
    function copyReport() {
        const textarea = document.querySelector('textarea[data-testid="stTextArea"]');
        if (textarea) {
            textarea.select();
            navigator.clipboard.writeText(textarea.value);
            alert('✅ 报告已复制到剪贴板！');
        }
    }
    </script>
    <button onclick="copyReport()" style="padding:8px 16px;background:#22c55e;color:white;border:none;border-radius:4px;cursor:pointer;">📋 复制报告</button>
    """
    st.markdown(copy_js, unsafe_allow_html=True)

# ==================== 主应用 ====================

def main():
    st.set_page_config(page_title='六合彩统计工具', layout='wide', initial_sidebar_state='expanded')
    
    # ====== 密码验证 ======
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    
    if not st.session_state['authenticated']:
        st.markdown("""
        <style>
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 40px;
            border-radius: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .login-title {
            text-align: center;
            color: white;
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 30px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="login-container"><div class="login-title">🔐 六合彩统计工具</div></div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            password = st.text_input('请输入密码', type='password', placeholder='输入访问密码')
            if st.button('🔑 进入系统', use_container_width=True):
                if password == get_app_password():
                    st.session_state['authenticated'] = True
                    st.rerun()
                else:
                    st.error('❌ 密码错误，请重试')
        return
    
    # ====== 主程序 ======
    if 'all_bets' not in st.session_state:
        st.session_state['all_bets'] = []
    if 'bet_history' not in st.session_state:
        st.session_state['bet_history'] = []
    if 'kaijiang_input' not in st.session_state:
        st.session_state['kaijiang_input'] = ''
    if 'bet_input' not in st.session_state:
        st.session_state['bet_input'] = ''
    if 'confirm_clear' not in st.session_state:
        st.session_state['confirm_clear'] = False
    
    # CSS样式（美化页面，修复表格滚动问题）
    st.markdown("""
    <style>
    .number-card {
        text-align: center;
        padding: 8px 4px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: bold;
        min-width: 40px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .number-card .num { font-size: 18px; }
    .number-card .amt { font-size: 10px; }
    .no-bet { background: #f1f5f9; color: #94a3b8; }
    .has-bet { background: #dbeafe; color: #1e40af; }
    .win-pingma { background: #dcfce7; color: #166534; }
    .win-tema { background: #fef3c7; color: #92400e; }
    .stats-card { padding: 10px; border-radius: 8px; text-align: center; }
    
    /* 修复表格样式 - 取消内部滚动，让整个页面滚动 */
    .detail-table {
        width: 100% !important;
        border-collapse: collapse !important;
        margin-bottom: 1rem !important;
        font-size: 14px !important;
    }
    .detail-table th {
        background-color: #3b82f6 !important;
        color: white !important;
        padding: 8px 6px !important;
        text-align: center !important;
        font-weight: bold !important;
        white-space: nowrap !important;
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
    }
    .detail-table td {
        padding: 6px 6px !important;
        text-align: center !important;
        border-bottom: 1px solid #e5e7eb !important;
        white-space: nowrap !important;
    }
    .detail-table tr:nth-child(even) {
        background-color: #f9fafb !important;
    }
    .detail-table tr:hover {
        background-color: #f3f4f6 !important;
    }
    .detail-table .total-row {
        background-color: #22c55e !important;
        color: white !important;
        font-weight: bold !important;
    }
    .detail-table .total-row td {
        border-bottom: none !important;
    }
    
    /* 卡片式布局样式 - 两列纵向排列 */
    .bet-card-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        width: 100%;
    }
    .bet-card {
        background: white;
        border-radius: 10px;
        padding: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 4px solid #3b82f6;
    }
    .bet-card.win {
        border-left-color: #22c55e;
        background: #f0fdf4;
    }
    .bet-card.lose {
        border-left-color: #ef4444;
        background: #fef2f2;
    }
    .bet-card.total {
        grid-column: span 2;
        background: #22c55e;
        color: white;
        border-left: none;
        text-align: center;
        font-weight: bold;
    }
    .bet-card .card-title {
        font-size: 16px;
        font-weight: bold;
        color: #1e40af;
        margin-bottom: 4px;
    }
    .bet-card.win .card-title {
        color: #166534;
    }
    .bet-card.lose .card-title {
        color: #991b1b;
    }
    .bet-card.total .card-title {
        color: white;
    }
    .bet-card .card-info {
        font-size: 12px;
        color: #64748b;
        margin-bottom: 2px;
    }
    .bet-card.total .card-info {
        color: rgba(255,255,255,0.8);
    }
    .bet-card .card-amount {
        font-size: 18px;
        font-weight: bold;
        color: #333;
        margin-top: 4px;
    }
    .bet-card.total .card-amount {
        color: white;
        font-size: 24px;
    }
    .bet-card .win-status {
        font-size: 14px;
        font-weight: bold;
        margin-top: 4px;
    }
    
    /* 响应式 - 手机上一列显示 */
    @media (max-width: 600px) {
        .bet-card-grid {
            grid-template-columns: 1fr;
        }
        .bet-card.total {
            grid-column: span 1;
        }
    }
    
    /* 滚动条样式 - 始终显示并美化 */
    html { overflow-y: scroll !important; }
    ::-webkit-scrollbar { width: 12px; height: 12px; }
    ::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
    ::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 6px; border: 2px solid #f1f5f9; }
    ::-webkit-scrollbar-thumb:hover { background: #64748b; }
    * { scrollbar-width: auto; scrollbar-color: #94a3b8 #f1f5f9; }
    
    /* 表格横向滚动容器 */
    .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
    div[data-testid="stTable"] { overflow-x: auto; max-width: 100%; }
    
    /* 手机端优化 */
    @media (max-width: 768px) {
        .main .block-container { padding-left: 10px !important; padding-right: 10px !important; }
        .detail-table { font-size: 12px !important; }
        .detail-table th, .detail-table td { padding: 4px 3px !important; }
        .number-card .num { font-size: 14px; }
        .number-card .amt { font-size: 9px; }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 顶部：期号和开奖号码输入
    st.header('🎯 六合彩统计工具')
    
    col1, col2 = st.columns([1, 2])
    with col1:
        qihao = st.text_input('期号', '')
    with col2:
        kaijiang_input = st.text_input('开奖号码（如：01,02,03,04,05,06+特码07）', 
                                      value=st.session_state['kaijiang_input'])
    
    # 解析开奖号码
    pingma_nums = []
    tema_num = ''
    tema_zodiac = ''
    has_kaijiang = bool(kaijiang_input.strip())
    if has_kaijiang:
        st.session_state['kaijiang_input'] = kaijiang_input
        pingma_nums, tema_num, tema_zodiac, all_kj_nums = parse_kaijiang(kaijiang_input)
    
    # 输入框 + 提交按钮
    st.subheader('📝 投注输入')
    
    def handle_submit():
        """处理投注提交"""
        bet_input_val = st.session_state.get('bet_input', '').strip()
        if bet_input_val:
            new_bets, errors = parse_bet_input(bet_input_val)

            if new_bets:
                st.session_state['all_bets'].extend(new_bets)

                total_submit_amount = sum(b['金额'] for b in new_bets)
                unique_numbers = set(b['号码'] for b in new_bets)

                st.session_state['bet_history'].append({
                    '时间': datetime.now().strftime('%H:%M:%S'),
                    '原始输入': bet_input_val,
                    '投注数': len(unique_numbers),
                    '总金额': total_submit_amount
                })

                st.session_state['last_success'] = f'✅ 成功添加 {len(unique_numbers)} 笔投注，总金额 ¥{total_submit_amount}'

            if errors:
                st.session_state['last_errors'] = errors

            # 有有效投注时才清空输入框，出错时保留内容方便修改
            if new_bets:
                st.session_state['bet_input'] = ''

    def clear_input():
        """清空输入框"""
        st.session_state['bet_input'] = ''

    def load_sample():
        """加载示例数据"""
        st.session_state['bet_input'] = '特码17投注100元\n平码05,17投注20元\n01/02/03数各20'

    bet_input = st.text_area('输入投注数据（支持多种格式）', height=100,
        placeholder='特码17投注100元\n平码05,17投注20元\n17/100\n01/02/03数各20\n龙，兔，各20\n11.23.35各10\n47=30\n特：18=20米\n狗平特500',
        key='bet_input')

    col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])

    with col_btn1:
        submit_btn = st.button('✅ 提交投注', use_container_width=True, on_click=handle_submit)
    with col_btn2:
        clear_input_btn = st.button('✕ 清空', use_container_width=True, on_click=clear_input)
    with col_btn3:
        sample_btn = st.button('📋 示例数据', use_container_width=True, on_click=load_sample)
    
    # 显示提交结果
    if 'last_success' in st.session_state and st.session_state['last_success']:
        st.success(st.session_state['last_success'])
        st.session_state['last_success'] = ''
    
    if 'last_errors' in st.session_state and st.session_state['last_errors']:
        st.warning('⚠️ 部分数据处理异常：')
        for e in st.session_state['last_errors']:
            st.warning(f'  - {e}')
        st.session_state['last_errors'] = []
    
    # 统计卡片
    if st.session_state['all_bets']:
        all_bets = st.session_state['all_bets']
        # 总投注额：所有投注记录金额之和（特肖不再展开，金额正确）
        total_amount = sum(b['金额'] for b in all_bets)
        total_count = len(all_bets)  # 总记录数
        total_unique = total_count   # 总笔数：每条投注记录算1笔（特肖不再展开）
        total_rows = len(set(b.get('行号', i) for i, b in enumerate(all_bets)))
        
        total_bonus = 0
        if has_kaijiang:
            results = calculate_results(all_bets, pingma_nums, tema_num)
            total_bonus = sum(r['奖金'] for r in results)
        
        st.subheader('📊 统计概览')
        col_stats = st.columns(6)
        stats = [
            ('💰 总投注', f'¥{total_amount:,}', '#64748b'),
            ('📝 总笔数', str(total_unique), '#6366f1'),
            ('🔢 记录数', str(total_count), '#8b5cf6'),
            ('📝 行数', str(total_rows), '#a855f7'),
            ('🎁 总奖金', f'¥{total_bonus:,}' if has_kaijiang else '待开奖', '#22c55e'),
            ('📈 盈亏', f'¥{total_bonus - total_amount:,}' if has_kaijiang else '-', '#ef4444' if (has_kaijiang and total_bonus - total_amount < 0) else '#22c55e')
        ]
        for i, (label, value, color) in enumerate(stats):
            with col_stats[i]:
                st.markdown(f'<div class="stats-card" style="background:{color}15;color:{color}"><div style="font-size:20px;font-weight:bold">{value}</div><div style="font-size:10px">{label}</div></div>', unsafe_allow_html=True)
    
    # 49号码网格 + 生肖统计
    if st.session_state['all_bets']:
        all_bets = st.session_state['all_bets']
        num_summary = {}
        for i in range(1, 50):
            num_str = str(i).zfill(2)
            num_summary[num_str] = {'amount': 0, 'is_win': '', 'bonus': 0}
        
        for bet in all_bets:
            num = bet['号码']
            if num.isdigit() and num in num_summary:
                num_summary[num]['amount'] += bet['金额']
        
        if has_kaijiang:
            tema_num_str = str(tema_num).zfill(2)
            for num_str in num_summary:
                if num_str == tema_num_str:
                    num_summary[num_str]['is_win'] = 'tema'
                    num_summary[num_str]['bonus'] = num_summary[num_str]['amount'] * ODDS_TABLE['特码']
                elif num_str in pingma_nums:
                    num_summary[num_str]['is_win'] = 'pingma'
                    num_summary[num_str]['bonus'] = num_summary[num_str]['amount'] * ODDS_TABLE['平码']
        
        st.subheader('🔢 49号码统计')
        grid_html = '<div style="display:grid;grid-template-columns:repeat(10,1fr);gap:4px;">'
        for i in range(1, 50):
            num_str = str(i).zfill(2)
            data = num_summary[num_str]
            amount = data['amount']
            
            if data['is_win'] == 'tema':
                style = 'win-tema'
            elif data['is_win'] == 'pingma':
                style = 'win-pingma'
            elif amount > 0:
                style = 'has-bet'
            else:
                style = 'no-bet'
            
            bonus_text = f'| ¥{data["bonus"]}' if data['bonus'] > 0 else ''
            grid_html += f'<div class="number-card {style}"><span class="num">{num_str}</span><span class="amt">¥{amount}{bonus_text}</span></div>'
        
        grid_html += '</div>'
        st.markdown(grid_html, unsafe_allow_html=True)
        
        zodiac_summary = {}
        for zodiac in ZODIAC_LIST:
            zodiac_summary[zodiac] = {'amount': 0, 'is_win': '', 'bonus': 0}
        
        # 从号码汇总计算生肖统计
        for num_str, data in num_summary.items():
            zodiac = NUMBER_TO_ZODIAC.get(num_str, '')
            if zodiac and data['amount'] > 0:
                zodiac_summary[zodiac]['amount'] += data['amount']
                if data['is_win'] == 'tema':
                    zodiac_summary[zodiac]['is_win'] = 'tema'
                    zodiac_summary[zodiac]['bonus'] += data['bonus']
        
        # 直接处理特肖投注记录（号码字段是生肖名称）
        for bet in all_bets:
            if bet['玩法'] == '特肖':
                zodiac = bet['号码']  # 特肖投注的号码字段是生肖名称
                if zodiac in zodiac_summary:
                    zodiac_summary[zodiac]['amount'] += bet['金额']
                    # 如果有开奖且中奖，更新中奖状态
                    if has_kaijiang:
                        tema_num_str = str(tema_num).zfill(2)
                        tema_zodiac = NUMBER_TO_ZODIAC.get(tema_num_str, '')
                        if zodiac == tema_zodiac:
                            zodiac_summary[zodiac]['is_win'] = 'tema'
                            zodiac_summary[zodiac]['bonus'] += bet['金额'] * ODDS_TABLE['特肖']
        
        zodiac_bets_exist = any(z['amount'] > 0 for z in zodiac_summary.values())
        if zodiac_bets_exist:
            st.subheader('🐉 生肖统计')
            zodiac_html = '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px;">'
            for zodiac in ZODIAC_LIST:
                data = zodiac_summary[zodiac]
                amount = data['amount']
                
                if data['is_win'] == 'tema':
                    style = 'win-tema'
                elif amount > 0:
                    style = 'has-bet'
                else:
                    style = 'no-bet'
                
                bonus_text = f'| ¥{data["bonus"]}' if data['bonus'] > 0 else ''
                zodiac_html += f'<div class="number-card {style}"><span class="num">{zodiac}</span><span class="amt">¥{amount}{bonus_text}</span></div>'
            
            zodiac_html += '</div>'
            st.markdown(zodiac_html, unsafe_allow_html=True)
    
    # 已输入的数据列表
    if st.session_state['bet_history']:
        st.subheader('📋 投注记录')
        df_history = pd.DataFrame(st.session_state['bet_history'])
        df_history = df_history[['时间', '原始输入', '投注数', '总金额']]
        df_history.index = range(1, len(df_history) + 1)
        st.table(df_history)
    
    # 投注明细（完整显示，不分页，使用HTML表格）
    if st.session_state['all_bets']:
        all_bets = st.session_state['all_bets']
        st.subheader('📊 投注明细')
        
        # 搜索功能
        search_col1, search_col2, search_col3 = st.columns([3, 2, 2])
        with search_col1:
            search_text = st.text_input('🔍 搜索号码或玩法', key='search_input')
        with search_col2:
            filter_type = st.selectbox('筛选类型', ['全部', '特码', '平码', '特肖'], key='filter_type')
        with search_col3:
            filter_play = st.selectbox('筛选玩法', ['全部', '特码', '平码', '特肖', '平码三中三', '平码二中二', '平特三连肖', '平特一肖'], key='filter_play')
        
        # 准备数据
        if has_kaijiang:
            results = calculate_results(all_bets, pingma_nums, tema_num)
            df = pd.DataFrame(results)
            df = df.reindex(columns=['号码', '类型', '玩法', '金额', '是否中奖', '奖金'])
        else:
            df = pd.DataFrame(all_bets)
            df = df.reindex(columns=['号码', '类型', '玩法', '金额'])
        
        # 应用筛选
        if search_text:
            df = df[df.apply(lambda row: any(search_text.lower() in str(val).lower() for val in row), axis=1)]
        # 修复类型筛选：特肖的类型是特码，但用户可能想筛选特肖玩法
        if filter_type != '全部':
            if filter_type == '特肖':
                df = df[df['玩法'] == '特肖']
            else:
                df = df[df['类型'] == filter_type]
        if filter_play != '全部':
            df = df[df['玩法'] == filter_play]
        
        # 按号码排序（号码在前，生肖在后按生肖顺序）
        df['sort_key'] = df['号码'].apply(lambda x: int(x) if x.isdigit() else 100 + ZODIAC_LIST.index(x) if x in ZODIAC_LIST else 200)
        df = df.sort_values('sort_key')
        df = df.drop('sort_key', axis=1)
        
        # 添加序号列
        df = df.reset_index(drop=True)
        df.insert(0, '序号', range(1, len(df) + 1))
        
        # 计算总计行
        total_amount = df['金额'].sum()
        total_bonus = df['奖金'].sum() if '奖金' in df.columns else 0
        
        # 添加总计行到DataFrame
        total_row = pd.DataFrame([{
            '序号': '总计',
            '号码': '-',
            '类型': '-',
            '玩法': f'{len(df)}笔',
            '金额': total_amount
        }])
        if has_kaijiang:
            total_row['奖金'] = total_bonus
        
        df = pd.concat([df, total_row], ignore_index=True)
        
        # 使用Streamlit原生表格显示（完整显示，无分页）
        st.table(df)
    
    # 底部功能按钮
    st.markdown('---')
    st.subheader('⚙️ 操作功能')
    
    all_bets = st.session_state['all_bets']
    
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
        if st.button('📄 生成结算报告', use_container_width=True):
            generate_report(all_bets, has_kaijiang, pingma_nums, tema_num, tema_zodiac)
    with col_btn2:
        if st.button('💾 保存记录', use_container_width=True):
            save_to_local_storage()
    with col_btn3:
        if st.button('📤 导出Excel', use_container_width=True):
            export_to_excel(all_bets, has_kaijiang, pingma_nums, tema_num)
    
    if st.button('📥 加载上次保存的数据', use_container_width=True):
        load_from_local_storage()
    
    # 底部：一键清空所有数据
    if all_bets:
        st.markdown('---')
        
        if not st.session_state['confirm_clear']:
            if st.button('🗑️ 清空所有数据', use_container_width=True, type='primary'):
                st.session_state['confirm_clear'] = True
        else:
            st.warning('⚠️ 确认清空所有投注数据吗？此操作不可撤销！')
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button('✅ 确认清空', use_container_width=True, key='btn_confirm'):
                    st.session_state['all_bets'] = []
                    st.session_state['bet_history'] = []
                    st.session_state['confirm_clear'] = False
                    st.rerun()
            with col_cancel:
                if st.button('❌ 取消', use_container_width=True, key='btn_cancel'):
                    st.session_state['confirm_clear'] = False

if __name__ == '__main__':
    main()
