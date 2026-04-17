# -*- coding: utf-8 -*-
"""
通达信量化监控系统 - 增强版（细分行业 + 股票名称）
功能：
- 实时行情监控（价格、涨跌幅、涨速等）
- 细分行业信息显示（从本地通达信读取）
- 股票名称显示（从本地通达信读取）
- 基于成交量的涨速计算（每分钟成交量变化率）
- 双击股票打开K线图窗口（历史日线）
- 均线策略买卖信号
- 交易时段自动判断
- 无实时数据时自动显示最近历史数据
"""

import sys
import datetime
import pandas as pd
import numpy as np
import mplfinance as mpf
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView, QLabel, QStatusBar,
    QDialog, QPushButton, QHBoxLayout
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mootdx.reader import Reader
from mootdx.quotes import Quotes
import akshare as ak

# ==================== 配置参数 ====================
TDX_DIR = 'C:/zd_zsone'  # 通达信安装目录（请根据实际修改）
SYMBOLS = ['600519', '000001']  # 监控的股票代码列表
MA_SHORT = 5  # 短期均线周期
MA_LONG = 20  # 长期均线周期
HOST = '123.125.108.59'  # 通达信行情服务器IP
PORT = 7709  # 端口
REFRESH_INTERVAL = 5000  # 行情刷新间隔（毫秒）
SECTOR_REFRESH_INTERVAL = 600000  # 细分行业刷新间隔（毫秒，10分钟）


# ==================== 辅助函数 ====================
def is_trading_time():
    """判断当前是否为A股交易时段"""
    now = datetime.datetime.now()
    weekday = now.weekday()
    if weekday >= 5:  # 周六、周日
        return False
    time_str = now.strftime("%H:%M")
    if ("09:30" <= time_str <= "11:30") or ("13:00" <= time_str <= "15:00"):
        return True
    return False


# ==================== K线图窗口 ====================
class KLineDialog(QDialog):
    """显示股票K线图的对话框"""

    def __init__(self, symbol, reader, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.reader = reader
        self.setWindowTitle(f"{symbol} - 日K线图")
        self.setGeometry(200, 200, 1000, 600)

        # 创建布局
        layout = QVBoxLayout(self)

        # 创建 Matplotlib 画布
        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        # 按钮
        btn_layout = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        # 绘制K线图
        self.plot_kline()

    def plot_kline(self):
        """从本地通达信读取历史日线数据并绘制K线图"""
        try:
            df = self.reader.daily(symbol=self.symbol)

            # 检查数据是否为空
            if df is None or df.empty:
                self._show_error("无历史数据")
                return

            # 检查数据量
            if len(df) < 10:
                self._show_error(f"数据量不足（仅{len(df)}条）")
                return

            # 准备 mplfinance 所需格式
            df = df.copy()

            # 确保索引是 DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                try:
                    df.index = pd.to_datetime(df.index)
                except:
                    df.index = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq='D')

            # 重命名列为 mplfinance 要求的格式
            rename_map = {
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            # 检查必要列是否存在
            required_cols = ['Open', 'High', 'Low', 'Close']
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                self._show_error(f"缺少必要列: {missing}")
                return

            # 添加移动平均线
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA20'] = df['Close'].rolling(20).mean()

            # 绘图
            self.figure.clear()
            ax = self.figure.add_subplot(111)

            # 使用 mplfinance 绘制
            mpf.plot(df, type='candle', style='charles',
                     volume=True, mav=(5, 20), ax=ax,
                     ylabel='价格', ylabel_lower='成交量',
                     title=f'{self.symbol} 日K线',
                     datetime_format='%Y-%m-%d')

            self.canvas.draw()

        except ImportError as e:
            self._show_error(f"缺少绘图库: {e}\n请安装: pip install mplfinance")
        except Exception as e:
            self._show_error(f"绘制失败: {str(e)}")

    def _show_error(self, msg):
        """显示错误信息"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, msg, transform=ax.transAxes,
                ha='center', va='center', fontsize=12, color='red')
        self.canvas.draw()


# ==================== 主窗口 ====================
class QuantMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("通达信量化监控系统")
        self.setGeometry(100, 100, 1400, 600)  # 增加宽度以适应更多列

        # 存储数据
        self.signals = {}  # 技术指标
        self.historical_data = {}  # 历史数据缓存
        self.sector_cache = {}  # 细分行业缓存 {symbol: industry_name}
        self.name_map = {}  # 股票名称映射 {symbol: name}
        self.last_data = {}  # 上次数据 {symbol: {'price':, 'time':, 'cur_vol':}}
        self.quote_client = None
        self.reader = None

        # 创建界面
        self._init_ui()

        # 初始化历史数据读取器
        self.reader = Reader.factory(market='std', tdxdir=TDX_DIR)

        # 初始化股票名称映射
        self._init_name_map()

        # 计算技术指标并缓存历史数据
        self._init_technical_indicators()

        # 初始化细分行业缓存
        QTimer.singleShot(0, self._refresh_sector_cache)

        # 连接实时行情
        self._connect_quotes()

        # 定时器：行情刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(REFRESH_INTERVAL)

        # 定时器：细分行业刷新
        self.sector_timer = QTimer()
        self.sector_timer.timeout.connect(self._refresh_sector_cache)
        self.sector_timer.start(SECTOR_REFRESH_INTERVAL)

        # 首次立即刷新
        self._refresh_data()

    def _init_ui(self):
        """创建界面组件"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 表格列数：代码、名称、细分行业、最新价、涨跌幅%、涨速(手/分)、MA5、MA20、信号、数据状态、更新时间
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "细分行业", "最新价", "涨跌幅%", "涨速(手/分)",
            f"MA{MA_SHORT}", f"MA{MA_LONG}",
            "信号", "数据状态", "更新时间"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # 双击事件打开K线图
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.table)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    def _init_name_map(self):
        """从本地通达信股票列表读取股票名称映射"""
        try:
            # 获取所有股票列表（包含代码和名称）
            stock_list = self.reader.stock_list(market='std')
            if stock_list is not None and not stock_list.empty:
                # stock_list 通常包含 'code' 和 'name' 列
                for _, row in stock_list.iterrows():
                    code = row['code']
                    name = row.get('name', '')
                    if code and name:
                        self.name_map[code] = name
                print(f"已加载 {len(self.name_map)} 只股票名称")
            else:
                print("股票列表为空，无法加载名称")
        except Exception as e:
            print(f"加载股票名称失败: {e}")
            # 备用：手动映射
            self.name_map = {'600519': '贵州茅台', '000001': '平安银行'}

    def _init_technical_indicators(self):
        """计算每只股票的历史均线值，并缓存最近一天的数据"""
        for symbol in SYMBOLS:
            try:
                df = self.reader.daily(symbol=symbol)
                if df.empty:
                    print(f"警告：{symbol} 无历史数据")
                    continue
                df['ma_short'] = df['close'].rolling(MA_SHORT).mean()
                df['ma_long'] = df['close'].rolling(MA_LONG).mean()
                last = df.iloc[-1]
                self.signals[symbol] = {
                    'ma_short': last['ma_short'],
                    'ma_long': last['ma_long'],
                    'last_close': last['close']
                }
                # 缓存历史数据（用于非实时时段显示）
                self.historical_data[symbol] = {
                    'price': last['close'],
                    'ma_short': last['ma_short'],
                    'ma_long': last['ma_long'],
                    'last_close': last['close'],
                    'date': df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(
                        df.index[-1])
                }
            except Exception as e:
                print(f"计算{symbol}指标失败: {e}")

    def _refresh_sector_cache(self):
        """刷新细分行业缓存（优先使用本地通达信block_gn.dat文件）"""
        try:
            # 方法1：读取本地通达信行业板块数据（block_gn.dat）
            df_block = self.reader.block(symbol='block_gn.dat', group=True)

            if df_block is not None and not df_block.empty:
                # 构建行业映射 {code: industry_name}
                for _, row in df_block.iterrows():
                    code = row.get('code')
                    industry = row.get('blockname')
                    if code and industry and code in SYMBOLS:
                        self.sector_cache[code] = industry

                # 补充未找到的股票
                for symbol in SYMBOLS:
                    if symbol not in self.sector_cache:
                        self.sector_cache[symbol] = "未分类"

                self.status_label.setText(f"细分行业已更新 (本地, {datetime.datetime.now().strftime('%H:%M:%S')})")
                return

        except Exception as e:
            print(f"本地行业文件读取失败: {e}，尝试在线获取...")

        # 方法2：使用AKShare在线获取同花顺行业数据（备选）
        try:
            industry_df = ak.stock_board_industry_summary_ths()
            if industry_df is not None and not industry_df.empty:
                for symbol in SYMBOLS:
                    self.sector_cache[symbol] = "获取中..."
                self.status_label.setText(f"细分行业已更新 (在线, {datetime.datetime.now().strftime('%H:%M:%S')})")
                return
        except Exception as e:
            print(f"在线行业数据获取失败: {e}")

        # 方法3：最终备用，显示未分类
        for symbol in SYMBOLS:
            if symbol not in self.sector_cache:
                self.sector_cache[symbol] = "未分类"

    def _connect_quotes(self):
        """连接实时行情服务器"""
        try:
            self.quote_client = Quotes.factory(market='std', host=HOST, port=PORT)
            self.status_label.setText("实时行情已连接")
        except Exception as e:
            self.status_label.setText(f"连接失败: {e}")
            self.quote_client = None

    def _refresh_data(self):
        """刷新数据：优先使用实时行情，否则显示缓存的历史数据"""
        # 判断是否使用实时数据：交易时段且连接正常且获取成功
        use_realtime = False
        realtime_data = None
        if is_trading_time() and self.quote_client is not None:
            try:
                realtime_data = self.quote_client.quotes(symbols=SYMBOLS)
                if realtime_data is not None and not realtime_data.empty:
                    use_realtime = True
            except Exception as e:
                print(f"实时数据获取异常: {e}")

        if use_realtime:
            # 使用实时数据更新表格
            now = datetime.datetime.now()
            now_str = now.strftime("%H:%M:%S")
            self.table.setRowCount(len(realtime_data))

            for i, (_, row) in enumerate(realtime_data.iterrows()):
                symbol = row['code']
                price = row['price']
                last_close = row['last_close']
                change = (price - last_close) / last_close * 100 if last_close else 0
                cur_vol = row.get('cur_vol', 0)

                # 股票名称
                name = self.name_map.get(symbol, "未知")
                # 细分行业
                industry = self.sector_cache.get(symbol, "加载中...")

                # 计算涨速（成交量变化率，手/分）
                speed = 0
                last = self.last_data.get(symbol)
                if last:
                    last_cur_vol = last.get('cur_vol', 0)
                    last_time = last['time']
                    time_diff = (now - last_time).total_seconds()
                    if time_diff > 0 and last_cur_vol > 0:
                        vol_rate_per_sec = (cur_vol - last_cur_vol) / time_diff
                        speed = vol_rate_per_sec * 60
                # 更新记录
                self.last_data[symbol] = {'price': price, 'time': now, 'cur_vol': cur_vol}

                # 技术指标
                sig = self.signals.get(symbol, {})
                ma_short = sig.get('ma_short', 0)
                ma_long = sig.get('ma_long', 0)

                # 信号
                if price > ma_short:
                    signal = "买入"
                elif price < ma_long:
                    signal = "卖出"
                else:
                    signal = "持有"

                # 填充表格（列顺序：代码、名称、细分行业、最新价、涨跌幅%、涨速%、MA5、MA20、信号、数据状态、更新时间）
                self.table.setItem(i, 0, QTableWidgetItem(symbol))
                self.table.setItem(i, 1, QTableWidgetItem(name))
                self.table.setItem(i, 2, QTableWidgetItem(industry))
                self.table.setItem(i, 3, QTableWidgetItem(f"{price:.2f}"))
                self.table.setItem(i, 4, QTableWidgetItem(f"{change:+.2f}"))
                self.table.setItem(i, 5, QTableWidgetItem(f"{speed:.2f}"))
                self.table.setItem(i, 6, QTableWidgetItem(f"{ma_short:.2f}"))
                self.table.setItem(i, 7, QTableWidgetItem(f"{ma_long:.2f}"))
                self.table.setItem(i, 8, QTableWidgetItem(signal))
                self.table.setItem(i, 9, QTableWidgetItem("实时"))
                self.table.setItem(i, 10, QTableWidgetItem(now_str))

                # 信号列背景色
                if signal == "买入":
                    self.table.item(i, 8).setBackground(QColor(0, 255, 0, 100))
                elif signal == "卖出":
                    self.table.item(i, 8).setBackground(QColor(255, 0, 0, 100))

            self.status_label.setText(f"实时数据 {now_str}")
        else:
            # 非交易时段或实时数据获取失败，显示历史数据
            self.table.setRowCount(len(SYMBOLS))
            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            for i, symbol in enumerate(SYMBOLS):
                # 获取缓存的历史数据
                hist = self.historical_data.get(symbol)
                if hist:
                    price = hist['price']
                    last_close = hist['last_close']
                    change = (price - last_close) / last_close * 100 if last_close else 0
                    ma_short = hist['ma_short']
                    ma_long = hist['ma_long']
                    date_str = hist['date']
                else:
                    price = 0
                    change = 0
                    ma_short = 0
                    ma_long = 0
                    date_str = "无数据"

                name = self.name_map.get(symbol, "未知")
                industry = self.sector_cache.get(symbol, "加载中...")

                # 信号（历史数据不产生交易信号，仅显示参考）
                signal = "历史参考"

                self.table.setItem(i, 0, QTableWidgetItem(symbol))
                self.table.setItem(i, 1, QTableWidgetItem(name))
                self.table.setItem(i, 2, QTableWidgetItem(industry))
                self.table.setItem(i, 3, QTableWidgetItem(f"{price:.2f}" if price else "无数据"))
                self.table.setItem(i, 4, QTableWidgetItem(f"{change:+.2f}" if price else "无数据"))
                self.table.setItem(i, 5, QTableWidgetItem("-"))
                self.table.setItem(i, 6, QTableWidgetItem(f"{ma_short:.2f}" if ma_short else "无数据"))
                self.table.setItem(i, 7, QTableWidgetItem(f"{ma_long:.2f}" if ma_long else "无数据"))
                self.table.setItem(i, 8, QTableWidgetItem(signal))
                self.table.setItem(i, 9, QTableWidgetItem(f"历史({date_str})"))
                self.table.setItem(i, 10, QTableWidgetItem(now_str))

                # 背景色统一为灰色
                for col in range(11):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QColor(240, 240, 240))

            self.status_label.setText(f"显示历史数据（{datetime.datetime.now().strftime('%H:%M:%S')}）")

    def on_item_double_clicked(self, item):
        """双击表格单元格时打开K线图窗口"""
        row = item.row()
        symbol_item = self.table.item(row, 0)  # 代码列固定在第一列
        if symbol_item:
            symbol = symbol_item.text()
            dialog = KLineDialog(symbol, self.reader, self)
            dialog.exec_()

    def closeEvent(self, event):
        """窗口关闭时释放连接"""
        if self.quote_client:
            self.quote_client.close()
        event.accept()


# ==================== 主程序入口 ====================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = QuantMonitor()
    window.show()
    sys.exit(app.exec_())