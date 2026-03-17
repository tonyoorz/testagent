import pandas as pd
from wordcloud import WordCloud, STOPWORDS
# 设置matplotlib后端为非GUI模式，避免macOS上的NSWindow线程问题
import matplotlib
matplotlib.use('Agg')  # 使用非GUI后端
import matplotlib.pyplot as plt
import os

# 强制设置为主进程，确保数据能正常加载
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

# 假设你的 data_processor.py 文件在同一目录下或 Python 路径中
from data_processor import load_test_data, load_defect_data, extract_english # 导入需要的函数

# --- 辅助函数：生成词云图 (添加停用词处理) ---
def generate_wordcloud(text_series, title, background_color='white', width=800, height=400, custom_stopwords=None):
    """
    根据 Pandas Series 中的文本数据生成并显示词云图，并忽略指定的停用词。

    Args:
        text_series (pd.Series): 包含文本数据的 Pandas Series。
        title (str): 词云图的标题。
        background_color (str): 词云图背景色。
        width (int): 图像宽度。
        height (int): 图像高度。
        custom_stopwords (set, optional): 用户自定义的需要忽略的词集合。默认为 None。
    """
    # 过滤掉空字符串、None、NaN 和 'Unknown'
    filtered_series = text_series.dropna().astype(str)
    filtered_series = filtered_series[filtered_series.str.strip() != '']
    filtered_series = filtered_series[filtered_series.str.lower() != 'unknown']

    if filtered_series.empty:
        print(f"警告: 过滤后没有有效数据用于生成 '{title}' 词云图。")
        return

    # 将 Series 中的所有文本合并为一个长字符串，用空格分隔
    # 在合并前可以先将文本转为小写，以便停用词匹配更准确
    text = ' '.join(filtered_series.str.lower().tolist())

    # 准备停用词集合
    # 复制默认停用词，避免直接修改全局 STOPWORDS
    stopwords = set(STOPWORDS)
    # 添加用户自定义的停用词（转换为小写）
    if custom_stopwords:
        stopwords.update({word.lower() for word in custom_stopwords})

    # 添加一些常见的、可能无意义的词（根据你的数据调整）
    additional_common_words = {'tsp', 'cn', 'iuk', 'dips', 'bmw', 'sys', 'mini', 'evo',
                               'manage', 'aisa', 'provide', 'test', 'via', 'connected',
                               'international', 'service', 'control', 'asia',
                               'remote', 'display'} # 示例 - 已更新
    stopwords.update(additional_common_words)


    # 创建词云对象，传入停用词
    wordcloud = WordCloud(width=width, height=height,
                          background_color=background_color,
                          stopwords=stopwords, # <--- 使用停用词集合
                          # font_path='path/to/your/chinese.ttf', # 如果需要中文支持
                          collocations=False, # 避免重复词组
                          ).generate(text)

    # 保存词云图
    plt.figure(figsize=(10, 5))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis("off")
    plt.title(title)
    
    # 生成文件名（去除特殊字符）
    safe_title = title.replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')
    filename = f"wordcloud_{safe_title}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"词云图已保存为: {filename}")

# --- 主程序 (调用修改后的函数) ---
if __name__ == '__main__':
    print("正在加载数据...")
    # 加载数据
    tdf = load_test_data()
    ddf = load_defect_data()
    print("数据加载完成。")

    # 定义你想要忽略的特定词汇
    my_custom_stopwords = {'china', 'chinese'} # 可以根据需要添加更多

    # --- 1. 生成测试热点词云图 (传入自定义停用词) ---
    print("\n正在生成测试热点词云图...")
    if 'tdf' in locals() and not tdf.empty and 'top_aida' in tdf.columns:
        generate_wordcloud(tdf['top_aida'],
                           title='测试热点 AIDA 分布 (已过滤停用词)',
                           custom_stopwords=my_custom_stopwords) # <--- 传入自定义停用词
    else:
        print("无法生成测试热点词云图：tdf 未加载、为空或缺少 'top_aida' 列。")


    # --- 2. 生成缺陷热点词云图 (传入自定义停用词) ---
    print("\n正在生成缺陷热点词云图 (高复杂度)...")
    if 'ddf' in locals() and not ddf.empty and 'complexity' in ddf.columns and 'top_aida' in ddf.columns:
        complex_defects = ddf[ddf['complexity'] == 'complex']
        if not complex_defects.empty:
             generate_wordcloud(complex_defects['top_aida'],
                                title='高复杂度缺陷热点 AIDA 分布 (已过滤停用词)',
                                custom_stopwords=my_custom_stopwords) # <--- 传入自定义停用词
        else:
             print("没有找到复杂度为 'complex' 的缺陷，无法生成缺陷热点词云图。")
    else:
        print("无法生成缺陷热点词云图：ddf 未加载、为空或缺少 'complexity' 或 'top_aida' 列。")

    print("\n词云图生成完毕。")
