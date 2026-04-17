import os


def parse_ebk_to_stock_codes(ebk_file_path):
    """
    解析通达信EBK文件，提取股票代码列表

    Args:
        ebk_file_path: EBK文件的路径

    Returns:
        list: 包含6位股票代码的列表，如 ['600519', '000001']
    """
    stock_codes = []

    # 检查文件是否存在
    if not os.path.exists(ebk_file_path):
        print(f"文件不存在: {ebk_file_path}")
        return stock_codes

    try:
        # EBK文件使用GBK或GB2312编码[citation:8]
        with open(ebk_file_path, 'r', encoding='gbk') as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # EBK文件格式：每行7位数字，第一位是市场标识，后六位是代码[citation:8]
            # 第1位：0表示深圳，1表示上海
            # 第2-7位：6位股票代码
            if len(line) >= 7 and line[:7].isdigit():
                full_code = line[:7]
                market_flag = full_code[0]
                code_6digit = full_code[1:7]  # 取后6位作为标准代码

                # 如果需要区分市场，可以保留市场信息
                market = "SH" if market_flag == '1' else "SZ"

                stock_codes.append(code_6digit)
                # 如果需要带市场后缀，可以使用: f"{code_6digit}.{market}"

        print(f"成功解析 {len(stock_codes)} 只股票")

    except UnicodeDecodeError:
        # 如果GBK解码失败，尝试UTF-8
        try:
            with open(ebk_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line and len(line) >= 7 and line[:7].isdigit():
                    stock_codes.append(line[1:7])
            print(f"成功解析 {len(stock_codes)} 只股票 (UTF-8编码)")
        except Exception as e:
            print(f"解析失败: {e}")
    except Exception as e:
        print(f"读取文件失败: {e}")

    return stock_codes


# ========== 使用示例 ==========
if __name__ == "__main__":
    # 替换为你的EBK文件路径
    ebk_path = r"C:\zd_zsone\T0002\blocknew\自选股.ebk"

    codes = parse_ebk_to_stock_codes(ebk_path)

    print("\n解析出的股票代码:")
    for code in codes[:20]:  # 只显示前20个
        print(code)

    if len(codes) > 20:
        print(f"... 共 {len(codes)} 只")

    # 可选：导出为CSV，方便导入量化系统
    import pandas as pd

    if codes:
        df = pd.DataFrame(codes, columns=['代码'])
        df.to_csv('stock_codes_from_ebk.csv', index=False, encoding='utf-8-sig')
        print("\n已导出到 stock_codes_from_ebk.csv")