# -*- coding: utf-8 -*-
"""
通达信量化监控系统 - 自动驾驶增强版（5次迭代最终版）
功能：
- 实时行情监控（价格、涨跌幅、成交量涨速）
- 细分行业（本地block_gn.dat / AKShare）
- 股票名称（AKShare）
- 技术指标：MA、MACD、RSI、KDJ、布林带宽度
- K线图（日K线、成交量、主力进出副图、最高最低标注、垂直参考线、全屏、键盘/鼠标交互）
- 主界面：表格显示、工具栏、右键菜单、K线预览
- 预警条件（价格、涨跌幅、成交量、主力净流入）
- 自选股与自定义板块管理（CSV导入/导出，可与通达信互通）
- 配置持久化（监控列表、指标开关、预警条件、自选股、板块等）
- 后台线程、日志窗口、系统托盘通知
- AI增强功能：
    - 自动因子挖掘（遗传编程+因子评估）
    - AI策略生成（支持本地Ollama / DeepSeek API / 模拟）
    - 真实回测引擎（支持滑点、佣金）与贝叶斯优化
    - 智能风控设置
- 自动驾驶功能：
    - 强化学习执行器（RLTrader）：使用PPO算法优化订单拆分，降低冲击成本
    - GAN压力测试器（GANStressTester）：生成极端市场情景，评估组合风险
    - 动态组合配置器（PortfolioOptimizer）：均值-方差/风险平价/Black-Litterman优化
    - 自动驾驶引擎（AutoPilotEngine）：定时执行调仓，无人值守
    - 自动驾驶设置界面：用户设定目标收益和最大回撤容忍度，启动/停止自动驾驶
"""

import sys
import datetime
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import mplfinance as mpf
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QWidget, QHeaderView, QLabel, QStatusBar,
    QDialog, QPushButton, QInputDialog, QCheckBox, QComboBox, QFormLayout,
    QDialogButtonBox, QMenu, QAction, QTextEdit, QDockWidget, QFileDialog,
    QSystemTrayIcon, QMessageBox, QLineEdit, QListWidget, QProgressBar,
    QGroupBox, QDoubleSpinBox, QSpinBox, QSplitter, QToolBar, QTabWidget,
    QProgressDialog
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QSettings, QSize, QMutex
from PyQt5.QtGui import QColor, QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from mootdx.reader import Reader
from mootdx.quotes import Quotes
import akshare as ak
import logging
import traceback
import importlib.util
import time
from typing import Dict, List, Optional, Tuple, Any, Callable
import os

# ==================== 设置日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quant_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('QuantMonitor')

# ==================== AI 模块导入（带友好提示） ====================
# 自动因子挖掘 (gplearn)
try:
    from gplearn.genetic import SymbolicTransformer
    from sklearn.preprocessing import StandardScaler
    GPLEARN_AVAILABLE = True
except Exception as e:
    GPLEARN_AVAILABLE = False
    logger.warning(f"gplearn导入失败: {e}，自动因子挖掘功能不可用。")

# 贝叶斯优化
try:
    from skopt import gp_minimize
    from skopt.space import Real, Integer
    SKOPT_AVAILABLE = True
except Exception as e:
    SKOPT_AVAILABLE = False
    logger.warning(f"scikit-optimize导入失败: {e}，贝叶斯优化功能不可用。")

# OpenAI (用于DeepSeek)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception as e:
    OPENAI_AVAILABLE = False
    logger.warning(f"openai导入失败: {e}，DeepSeek API功能不可用。")

# Ollama
try:
    import ollama
    OLLAMA_AVAILABLE = True
except Exception as e:
    OLLAMA_AVAILABLE = False
    logger.warning(f"ollama导入失败: {e}，本地模型功能不可用。")

# 强化学习 (stable-baselines3, gym)
RL_AVAILABLE = False
try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    import gym
    from gym import spaces
    RL_AVAILABLE = True
except Exception as e:
    logger.warning(f"stable-baselines3导入失败: {e}，强化学习执行功能不可用。")

# PyTorch (GAN)
TORCH_AVAILABLE = False
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except Exception as e:
    logger.warning(f"torch导入失败: {e}，GAN压力测试功能不可用。")

# cvxpy (组合优化)
CVXPY_AVAILABLE = False
try:
    import cvxpy as cp
    CVXPY_AVAILABLE = True
except Exception as e:
    logger.warning(f"cvxpy导入失败: {e}，组合优化功能不可用。")

# ==================== 设置 matplotlib 中文字体 ====================
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ==================== 默认配置 ====================
DEFAULT_SETTINGS = {
    'tdx_dir': 'C:/zd_zsone',
    'symbols': ['600519', '000001'],
    'ma_short': 5,
    'ma_long': 20,
    'host': '123.125.108.59',
    'port': 7709,
    'refresh_interval': 5000,
    'sector_refresh_interval': 600000,
    'show_macd': True,
    'show_rsi': True,
    'show_kdj': False,
    'show_boll': False,
    'enable_notify': True,
    'favorites': [],
    'alerts': [],
    'risk_stop_mult': 2.0,
    'risk_per_trade': 0.02,
    'risk_use_gnn': False,
    'commission': 0.0003,  # 佣金率
    'slippage': 0.001,  # 滑点
}

# ==================== 表格列索引常量 ====================
class TableCol:
    CODE = 0
    NAME = 1
    INDUSTRY = 2
    PRICE = 3
    CHANGE = 4
    SPEED = 5
    MA_SHORT = 6
    MA_LONG = 7
    MACD = 8
    RSI = 9
    KDJ_K = 10
    BOLL_WIDTH = 11
    SIGNAL = 12
    STATUS = 13
    UPDATE_TIME = 14

# ==================== AI 辅助类定义 ====================

class AutoFactorMiner:
    """自动因子挖掘（基于遗传编程）"""

    def __init__(self, population_size=2000, generations=20):
        self.population_size = population_size
        self.generations = generations
        self.model = None

    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成基础特征（不含未来信息）"""
        features = pd.DataFrame(index=df.index)
        features['close'] = df['close']
        features['volume'] = df['volume']
        features['high'] = df['high']
        features['low'] = df['low']
        features['ma5'] = df['close'].rolling(5).mean()
        features['ma20'] = df['close'].rolling(20).mean()
        features['volatility'] = df['close'].pct_change().rolling(20).std()
        features['return'] = df['close'].pct_change()
        features.fillna(0, inplace=True)
        return features

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """训练因子挖掘模型"""
        if not GPLEARN_AVAILABLE:
            raise ImportError("gplearn未安装")
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        self.model = SymbolicTransformer(
            population_size=self.population_size,
            generations=self.generations,
            function_set=('add', 'sub', 'mul', 'div', 'sqrt', 'log', 'abs'),
            metric='pearson',
            parsimony_coefficient=0.01,
            random_state=42
        )
        self.model.fit(X_scaled, y)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """生成新因子"""
        if not GPLEARN_AVAILABLE:
            raise ImportError("gplearn未安装")
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        new_factors = self.model.transform(X_scaled)
        for i, col in enumerate(new_factors.T):
            X[f'alpha_{i}'] = col
        return X

    def evaluate_factor(self, X: pd.DataFrame, factor_name: str, y: pd.Series) -> float:
        """评估因子效果（IC）"""
        factor = X[factor_name]
        ic = factor.corr(y)
        return ic


class StrategyGenerator:
    """策略生成器基类"""

    def generate(self, description: str) -> str:
        raise NotImplementedError


class MockStrategyGenerator(StrategyGenerator):
    """模拟生成器"""

    def generate(self, description: str) -> str:
        return f"""# 模拟生成的策略代码
# 描述：{description}
class Strategy:
    def __init__(self, params):
        self.ma_short = params.get('ma_short', 5)
        self.ma_long = params.get('ma_long', 20)

    def next(self, data):
        # 示例逻辑
        if data['close'][-1] > data['ma_short'][-1]:
            return 'buy'
        return 'hold'
"""


class OllamaStrategyGenerator(StrategyGenerator):
    """Ollama本地模型"""

    def __init__(self, model="qwen2.5-coder:7b"):
        self.model = model
        if not OLLAMA_AVAILABLE:
            raise ImportError("ollama未安装")

    def generate(self, description: str) -> str:
        prompt = f"""你是一个量化策略专家。请根据以下描述生成Python策略代码，继承自BaseStrategy，包含__init__和next方法。只返回代码，不要解释。

描述：{description}
"""
        try:
            response = ollama.generate(model=self.model, prompt=prompt, options={"temperature": 0.2})
            code = response.get('response', '')
            if '```python' in code:
                code = code.split('```python')[1].split('```')[0].strip()
            return code
        except Exception as e:
            return f"错误：{e}"


class DeepSeekStrategyGenerator(StrategyGenerator):
    """DeepSeek API"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        if not OPENAI_AVAILABLE:
            raise ImportError("openai未安装")
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def generate(self, description: str) -> str:
        prompt = f"生成量化策略代码：{description}"
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            code = response.choices[0].message.content
            if '```python' in code:
                code = code.split('```python')[1].split('```')[0].strip()
            return code
        except Exception as e:
            return f"错误：{e}"


class BacktestEngine:
    """真实回测引擎（基于pandas）"""

    def __init__(self, strategy_class, commission: float = 0.0003, slippage: float = 0.001):
        self.strategy_class = strategy_class
        self.commission = commission
        self.slippage = slippage

    def run(self, data: pd.DataFrame, initial_capital: float = 1e6, **params) -> Dict:
        """
        执行回测
        data: 包含 'open', 'high', 'low', 'close', 'volume' 的DataFrame，索引为日期
        params: 策略参数
        返回回测结果字典
        """
        df = data.copy()
        df.sort_index(inplace=True)
        df['returns'] = df['close'].pct_change()

        # 初始化策略
        strategy = self.strategy_class(params)

        # 模拟持仓
        position = 0.0
        capital = initial_capital
        trades = []
        last_signal = 'hold'

        # 净值曲线
        equity_curve = [initial_capital]

        for i in range(1, len(df)):
            # 构建当前可用的数据窗口
            current_data = {
                'open': df['open'].iloc[:i + 1],
                'high': df['high'].iloc[:i + 1],
                'low': df['low'].iloc[:i + 1],
                'close': df['close'].iloc[:i + 1],
                'volume': df['volume'].iloc[:i + 1],
            }
            # 获取信号
            signal = strategy.next(current_data)

            # 处理信号
            if signal == 'buy' and position == 0:
                # 以当前收盘价买入（考虑滑点）
                price = df['close'].iloc[i] * (1 + self.slippage)
                shares = int(capital / price)
                if shares > 0:
                    cost = shares * price * (1 + self.commission)
                    capital -= cost
                    position = shares
                    trades.append(('buy', df.index[i], price, shares))
                    last_signal = 'buy'
            elif signal == 'sell' and position > 0:
                price = df['close'].iloc[i] * (1 - self.slippage)
                proceeds = position * price * (1 - self.commission)
                capital += proceeds
                trades.append(('sell', df.index[i], price, position))
                position = 0
                last_signal = 'sell'

            # 计算当日净值
            current_value = capital + position * df['close'].iloc[i]
            equity_curve.append(current_value)

        # 最终平仓
        if position > 0:
            price = df['close'].iloc[-1] * (1 - self.slippage)
            proceeds = position * price * (1 - self.commission)
            capital += proceeds
            trades.append(('sell', df.index[-1], price, position))
            current_value = capital
            equity_curve[-1] = current_value

        # 计算策略收益率序列（每日净值）
        equity_series = pd.Series(equity_curve, index=df.index)
        total_return = (equity_series.iloc[-1] / initial_capital - 1) * 100

        # 夏普比率
        daily_returns = equity_series.pct_change().dropna()
        if len(daily_returns) > 0 and daily_returns.std() != 0:
            sharpe = (daily_returns.mean() - 0) / daily_returns.std() * np.sqrt(252)
        else:
            sharpe = 0.0

        # 最大回撤
        peak = equity_series.expanding().max()
        drawdown = (equity_series - peak) / peak
        max_dd = drawdown.min() * 100

        return {
            'total_return': total_return,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'final_capital': equity_series.iloc[-1],
            'trades': trades,
            'equity_curve': equity_series
        }

    def optimize(self, data: pd.DataFrame, param_space: Dict, n_calls: int = 30, initial_capital: float = 1e6) -> Tuple[
        Dict, float]:
        """贝叶斯优化"""
        if not SKOPT_AVAILABLE:
            raise ImportError("scikit-optimize未安装")

        def objective(params):
            param_dict = {}
            for k, v in zip(param_space.keys(), params):
                param_dict[k] = v
            result = self.run(data, initial_capital, **param_dict)
            return -result['sharpe']  # 最小化负夏普

        # 准备搜索空间
        dimensions = []
        for k, v in param_space.items():
            if isinstance(v, tuple):
                dimensions.append(Real(v[0], v[1], name=k))
            elif isinstance(v, int):
                dimensions.append(Integer(v, v, name=k))
            else:
                dimensions.append(Real(v, v, name=k))
        res = gp_minimize(objective, dimensions, n_calls=n_calls, random_state=42)
        best_params = {k: v for k, v in zip(param_space.keys(), res.x)}
        return best_params, -res.fun


class RiskManager:
    """智能风控管理器"""

    def __init__(self, initial_capital=1e6):
        self.capital = initial_capital
        self.stop_loss_mult = 2.0
        self.risk_per_trade = 0.02
        self.use_gnn = False

    def dynamic_stop_loss(self, entry_price: float, atr: float) -> float:
        """动态止损价"""
        return entry_price - self.stop_loss_mult * atr

    def max_position_size(self, entry_price: float, atr: float) -> float:
        """最大仓位（股数）"""
        risk_amount = self.capital * self.risk_per_trade
        risk_per_share = self.stop_loss_mult * atr
        if risk_per_share <= 0:
            return 0
        shares = risk_amount / risk_per_share
        max_shares = self.capital / entry_price
        return min(shares, max_shares)


# ==================== 自动驾驶模块 ====================

# ---------- 强化学习执行器 ----------
if RL_AVAILABLE:
    class TradingEnv(gym.Env):
        """模拟交易环境，用于训练执行智能体"""

        def __init__(self, data, volume, price_slippage_model):
            super().__init__()
            self.data = data  # 历史OHLCV数据，需包含'close','volatility'
            self.volume = volume
            self.price_model = price_slippage_model
            self.current_step = 0
            self.remaining_volume = volume
            self.action_space = spaces.Discrete(10)  # 拆分为10个时间片
            self.observation_space = spaces.Box(low=0, high=1, shape=(3,), dtype=np.float32)

        def reset(self):
            self.current_step = 0
            self.remaining_volume = self.volume
            return self._get_obs()

        def step(self, action):
            trade_ratio = (action + 1) / 10
            trade_volume = min(self.remaining_volume, trade_ratio * self.volume)
            price = self.data['close'].iloc[self.current_step] * (1 + self.price_model.impact(trade_volume))
            cost = trade_volume * price
            self.remaining_volume -= trade_volume
            self.current_step += 1
            reward = -cost
            done = self.remaining_volume <= 0 or self.current_step >= len(self.data)
            return self._get_obs(), reward, done, {}

        def _get_obs(self):
            obs = np.array([
                self.current_step / len(self.data),
                self.remaining_volume / self.volume,
                self.data['volatility'].iloc[self.current_step]
            ])
            return obs

    class SimplePriceImpact:
        """简单的价格冲击模型"""

        def __init__(self, impact_coeff=0.001):
            self.impact_coeff = impact_coeff

        def impact(self, volume):
            return volume * self.impact_coeff

    class RLTrader:
        """强化学习交易执行器"""

        def __init__(self, model_path=None):
            self.model = None
            if model_path and os.path.exists(model_path):
                self.model = PPO.load(model_path)

        def train(self, data, volume, price_model, total_timesteps=10000):
            env = TradingEnv(data, volume, price_model)
            env = DummyVecEnv([lambda: env])
            self.model = PPO('MlpPolicy', env, verbose=1)
            self.model.learn(total_timesteps=total_timesteps)

        def execute(self, data, volume, price_model):
            """执行下单，返回成交明细"""
            if self.model is None:
                raise RuntimeError("模型未训练或未加载")
            env = TradingEnv(data, volume, price_model)
            obs = env.reset()
            done = False
            trades = []
            while not done:
                action, _ = self.model.predict(obs)
                obs, reward, done, _ = env.step(action)
                trades.append({
                    'step': env.current_step,
                    'volume': volume,
                    'price': data['close'].iloc[env.current_step - 1]
                })
            return trades
else:
    class RLTrader:
        def __init__(self, *args, **kwargs):
            raise ImportError("强化学习库未安装")
        def train(self, *args, **kwargs):
            raise ImportError("强化学习库未安装")
        def execute(self, *args, **kwargs):
            raise ImportError("强化学习库未安装")

# ---------- GAN 压力测试器 ----------
if TORCH_AVAILABLE:
    class Generator(nn.Module):
        def __init__(self, input_dim, output_dim):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, 128),
                nn.ReLU(),
                nn.Linear(128, 256),
                nn.ReLU(),
                nn.Linear(256, output_dim),
                nn.Tanh()
            )

        def forward(self, z):
            return self.net(z)

    class Discriminator(nn.Module):
        def __init__(self, input_dim):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, 256),
                nn.ReLU(),
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Linear(128, 1),
                nn.Sigmoid()
            )

        def forward(self, x):
            return self.net(x)

    class GANStressTester:
        def __init__(self, latent_dim=100, device='cpu'):
            self.latent_dim = latent_dim
            self.device = device
            self.generator = Generator(latent_dim, 1).to(device)
            self.discriminator = Discriminator(1).to(device)
            self.g_optim = optim.Adam(self.generator.parameters(), lr=0.0002)
            self.d_optim = optim.Adam(self.discriminator.parameters(), lr=0.0002)
            self.criterion = nn.BCELoss()

        def train(self, real_data, epochs=1000):
            real_data = torch.FloatTensor(real_data).view(-1, 1).to(self.device)
            # 归一化
            mean = real_data.mean()
            std = real_data.std() + 1e-8
            real_data = (real_data - mean) / std
            for epoch in range(epochs):
                real_labels = torch.ones(real_data.size(0), 1).to(self.device)
                fake_labels = torch.zeros(real_data.size(0), 1).to(self.device)
                d_real_loss = self.criterion(self.discriminator(real_data), real_labels)
                z = torch.randn(real_data.size(0), self.latent_dim).to(self.device)
                fake_data = self.generator(z)
                d_fake_loss = self.criterion(self.discriminator(fake_data.detach()), fake_labels)
                d_loss = d_real_loss + d_fake_loss
                self.d_optim.zero_grad()
                d_loss.backward()
                self.d_optim.step()

                z = torch.randn(real_data.size(0), self.latent_dim).to(self.device)
                fake_data = self.generator(z)
                g_loss = self.criterion(self.discriminator(fake_data), real_labels)
                self.g_optim.zero_grad()
                g_loss.backward()
                self.g_optim.step()
            # 保存归一化参数
            self.data_mean = mean.item()
            self.data_std = std.item()

        def generate_scenarios(self, n_scenarios=1000, seq_length=100):
            scenarios = []
            for _ in range(n_scenarios):
                z = torch.randn(seq_length, self.latent_dim).to(self.device)
                with torch.no_grad():
                    fake = self.generator(z).cpu().numpy().flatten()
                fake = fake * self.data_std + self.data_mean
                # 放大极端情况
                extreme = fake * 3
                scenarios.append(extreme)
            return np.array(scenarios)

        def stress_test(self, portfolio_returns, scenarios):
            # 假设 portfolio_returns 是组合历史收益率序列
            # 场景叠加
            stressed_returns = portfolio_returns + scenarios.mean(axis=0)
            cumulative = (1 + stressed_returns).cumprod()
            max_dd = (cumulative.cummax() - cumulative).max()
            return max_dd
else:
    class GANStressTester:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch未安装")
        def train(self, *args, **kwargs):
            raise ImportError("PyTorch未安装")
        def generate_scenarios(self, *args, **kwargs):
            raise ImportError("PyTorch未安装")
        def stress_test(self, *args, **kwargs):
            raise ImportError("PyTorch未安装")

# ---------- 动态组合配置器 ----------
if CVXPY_AVAILABLE:
    class PortfolioOptimizer:
        """组合优化器，支持均值-方差、风险平价、Black-Litterman"""

        def __init__(self, expected_returns, cov_matrix, risk_free_rate=0.02):
            self.expected_returns = expected_returns
            self.cov_matrix = cov_matrix
            self.risk_free_rate = risk_free_rate

        def mean_variance(self, target_return, max_weight=1.0):
            n = len(self.expected_returns)
            w = cp.Variable(n)
            ret = self.expected_returns @ w
            risk = cp.quad_form(w, self.cov_matrix)
            constraints = [cp.sum(w) == 1, w >= 0, w <= max_weight, ret >= target_return]
            obj = cp.Minimize(risk)
            prob = cp.Problem(obj, constraints)
            prob.solve()
            if w.value is None:
                return None
            return w.value

        def risk_parity(self):
            n = len(self.expected_returns)
            w = cp.Variable(n)
            risk_contributions = cp.multiply(w, self.cov_matrix @ w) / cp.quad_form(w, self.cov_matrix)
            constraints = [cp.sum(w) == 1, w >= 0]
            obj = cp.Minimize(cp.sum_squares(risk_contributions - 1 / n))
            prob = cp.Problem(obj, constraints)
            prob.solve()
            if w.value is None:
                return None
            return w.value

        def black_litterman(self, views, confidences):
            tau = 0.025
            Pi = self.expected_returns
            P = views
            Q = confidences
            Omega = np.diag(np.diag(P @ self.cov_matrix @ P.T) / confidences)
            mu_bl = Pi + tau * self.cov_matrix @ P.T @ np.linalg.inv(tau * P @ self.cov_matrix @ P.T + Omega) @ (Q - P @ Pi)
            return mu_bl
else:
    class PortfolioOptimizer:
        def __init__(self, *args, **kwargs):
            raise ImportError("cvxpy未安装")
        def mean_variance(self, *args, **kwargs):
            raise ImportError("cvxpy未安装")
        def risk_parity(self, *args, **kwargs):
            raise ImportError("cvxpy未安装")
        def black_litterman(self, *args, **kwargs):
            raise ImportError("cvxpy未安装")

class AutoPortfolioManager:
    """结合用户目标和风险约束的组合管理器"""

    def __init__(self, optimizer, rl_trader, stress_tester, target_return, max_drawdown):
        self.optimizer = optimizer
        self.rl_trader = rl_trader
        self.stress_tester = stress_tester
        self.target_return = target_return
        self.max_drawdown = max_drawdown
        self.current_weights = None

    def optimize(self, data: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """根据最新数据计算目标权重，返回权重字典"""
        # 对齐日期并计算收益率
        returns_dict = {}
        for sym, df in data.items():
            if df is not None and not df.empty:
                returns_dict[sym] = df['close'].pct_change()
        df_returns = pd.DataFrame(returns_dict).dropna()
        if df_returns.empty:
            raise ValueError("无有效收益率数据")

        expected_returns = df_returns.mean() * 252
        cov_matrix = df_returns.cov() * 252
        self.optimizer.expected_returns = expected_returns
        self.optimizer.cov_matrix = cov_matrix

        target = self.target_return / 100
        weights_array = self.optimizer.mean_variance(target)
        if weights_array is None:
            weights_array = self.optimizer.risk_parity()
            if weights_array is None:
                raise ValueError("无法找到可行权重")

        # 转换为字典，保持顺序与expected_returns.index一致
        weights_dict = dict(zip(expected_returns.index, weights_array))

        # 压力测试验证（如果有stress_tester）
        if self.stress_tester is not None:
            # 计算组合历史收益率
            portfolio_returns = df_returns @ weights_array
            scenarios = self.stress_tester.generate_scenarios(n_scenarios=1000, seq_length=len(portfolio_returns))
            max_dd = self.stress_tester.stress_test(portfolio_returns.values, scenarios)
            if max_dd < -self.max_drawdown / 100:
                # 不符合风险要求，调整：使用最小方差组合
                weights_array = self.optimizer.mean_variance(0)
                if weights_array is None:
                    weights_array = self.optimizer.risk_parity()
                weights_dict = dict(zip(expected_returns.index, weights_array))
        return weights_dict

    def rebalance(self, current_positions: Dict[str, float], target_weights: Dict[str, float],
                  prices: Dict[str, float]) -> List[Dict]:
        """执行调仓，返回订单列表"""
        total_value = sum(current_positions.values())
        if total_value == 0:
            total_value = 1e6  # 初始资金假设

        orders = []
        for symbol, target_w in target_weights.items():
            target_value = target_w * total_value
            current_value = current_positions.get(symbol, 0.0)
            delta = target_value - current_value
            if abs(delta) < 1e-6:
                continue
            direction = 'buy' if delta > 0 else 'sell'
            price = prices.get(symbol, 0)
            if price <= 0:
                continue
            volume = abs(delta) / price
            # 使用RL执行器拆分订单（如果可用）
            if self.rl_trader is not None:
                # 获取该股票的历史数据（简化，这里使用传入的data）
                # 实际应传入历史数据，此处仅为示例
                trades = self.rl_trader.execute(None, volume, None)  # 需要实现
            else:
                trades = [{'volume': volume, 'price': price}]
            orders.append({
                'symbol': symbol,
                'direction': direction,
                'trades': trades
            })
        return orders

class AutoPilotEngine(QThread):
    """自动驾驶引擎，在后台线程中运行"""
    status_signal = pyqtSignal(str)
    order_signal = pyqtSignal(dict)

    def __init__(self, manager, portfolio, data_feeder, interval_seconds=3600):
        super().__init__()
        self.manager = manager
        self.portfolio = portfolio
        self.data_feeder = data_feeder
        self.interval = interval_seconds
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            try:
                data = self.data_feeder.get_latest_data()
                if not data:
                    self.status_signal.emit("无法获取数据，跳过本轮调仓")
                    time.sleep(60)
                    continue
                target_weights = self.manager.optimize(data)
                # 获取最新价格
                prices = {}
                for sym in target_weights.keys():
                    quotes = self.data_feeder.latest_quotes.get(sym, {})
                    prices[sym] = quotes.get('price', 0)
                orders = self.manager.rebalance(self.portfolio, target_weights, prices)
                for order in orders:
                    self.order_signal.emit(order)
                    self.status_signal.emit(f"执行调仓: {order}")
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                self.status_signal.emit(f"自动驾驶出错: {e}")
                time.sleep(60)

    def stop(self):
        self.running = False
        self.wait()

# ---------- 自动驾驶设置界面 ----------
class AutoPilotDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.engine = None
        self.setWindowTitle("自动驾驶设置")
        self.setGeometry(400, 300, 600, 500)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.target_return = QDoubleSpinBox()
        self.target_return.setRange(-100, 100)
        self.target_return.setValue(15.0)
        self.target_return.setSuffix("%")
        form.addRow("目标年化收益:", self.target_return)

        self.max_drawdown = QDoubleSpinBox()
        self.max_drawdown.setRange(1, 50)
        self.max_drawdown.setValue(20)
        self.max_drawdown.setSuffix("%")
        form.addRow("最大回撤容忍度:", self.max_drawdown)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.5, 24)
        self.interval.setValue(1.0)
        self.interval.setSuffix("小时")
        form.addRow("调仓间隔:", self.interval)

        self.use_rl = QCheckBox("启用强化学习执行")
        self.use_rl.setChecked(RL_AVAILABLE)
        self.use_rl.setEnabled(RL_AVAILABLE)
        form.addRow(self.use_rl)

        self.use_gan = QCheckBox("启用GAN压力测试")
        self.use_gan.setChecked(TORCH_AVAILABLE)
        self.use_gan.setEnabled(TORCH_AVAILABLE)
        form.addRow(self.use_gan)

        layout.addLayout(form)

        self.start_btn = QPushButton("启动自动驾驶")
        self.start_btn.clicked.connect(self.start_autopilot)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止自动驾驶")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_autopilot)
        layout.addWidget(self.stop_btn)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(QLabel("运行日志:"))
        layout.addWidget(self.log_text)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(1000)

    def start_autopilot(self):
        if self.use_rl.isChecked() and not RL_AVAILABLE:
            QMessageBox.critical(self, "错误", "强化学习执行需要安装 stable-baselines3")
            return
        if self.use_gan.isChecked() and not TORCH_AVAILABLE:
            QMessageBox.critical(self, "错误", "GAN压力测试需要安装 PyTorch")
            return
        if not CVXPY_AVAILABLE:
            QMessageBox.critical(self, "错误", "组合优化需要安装 cvxpy")
            return

        data_feeder = self.parent
        portfolio = self.parent.get_current_positions()

        rl_trader = None
        if self.use_rl.isChecked():
            model_path = "rl_trader_model.zip"
            if os.path.exists(model_path):
                rl_trader = RLTrader(model_path)
            else:
                self.log_text.append("未找到强化学习模型，将使用普通执行器")

        stress_tester = None
        if self.use_gan.isChecked():
            stress_tester = GANStressTester() if TORCH_AVAILABLE else None

        data = self.parent.get_latest_data()
        if not data:
            QMessageBox.warning(self, "警告", "无法获取历史数据，请等待数据加载完成后再启动")
            return
        returns_df = pd.DataFrame()
        for sym, df in data.items():
            if df is not None and not df.empty:
                returns_df[sym] = df['close'].pct_change()
        returns_df = returns_df.dropna()
        if returns_df.empty:
            QMessageBox.warning(self, "警告", "历史数据不足，无法进行优化")
            return
        expected_returns = returns_df.mean() * 252
        cov_matrix = returns_df.cov() * 252
        optimizer = PortfolioOptimizer(expected_returns, cov_matrix)

        manager = AutoPortfolioManager(optimizer, rl_trader, stress_tester,
                                       self.target_return.value(), self.max_drawdown.value())

        self.engine = AutoPilotEngine(manager, portfolio, data_feeder, self.interval.value() * 3600)
        self.engine.status_signal.connect(self.log_text.append)
        self.engine.order_signal.connect(lambda x: self.log_text.append(str(x)))
        self.engine.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_text.append("自动驾驶已启动")

    def stop_autopilot(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_text.append("自动驾驶已停止")

    def update_status(self):
        if self.engine and self.engine.isRunning():
            self.log_text.append("自动驾驶运行中...")

# ==================== 辅助函数 ====================
def is_trading_time() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    time_str = now.strftime("%H:%M")
    if ("09:30" <= time_str <= "11:30") or ("13:00" <= time_str <= "15:00"):
        return True
    return False

def safe_eval(condition: str, context: Dict) -> bool:
    allowed_names = {
        'price': context.get('price', 0),
        'change': context.get('change', 0),
        'volume': context.get('volume', 0),
        'abs': abs,
        'max': max,
        'min': min,
        'round': round,
    }
    code = compile(condition, '<string>', 'eval')
    for name in code.co_names:
        if name not in allowed_names:
            raise NameError(f"禁止使用变量: {name}")
    return eval(code, {"__builtins__": {}}, allowed_names)

# ==================== 后台数据获取线程 ====================
class DataFetcher(QThread):
    data_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, symbols, host, port):
        super().__init__()
        self.symbols = symbols
        self.host = host
        self.port = port
        self.client = None
        self.running = True
        self.retry_count = 0
        self.mutex = QMutex()

    def run(self):
        while self.running:
            try:
                self.mutex.lock()
                if self.client is None:
                    self.client = Quotes.factory(market='std', host=self.host, port=self.port)
                self.mutex.unlock()
                quotes = self.client.quotes(symbols=self.symbols)
                if quotes is not None and not quotes.empty:
                    self.data_ready.emit(quotes)
                    self.retry_count = 0
                else:
                    self.retry_count += 1
                    if self.retry_count >= 3:
                        self.error_occurred.emit("连续多次获取数据为空，可能网络问题")
                        self.retry_count = 0
            except Exception as e:
                self.error_occurred.emit(str(e))
                self.mutex.lock()
                if self.client:
                    try:
                        self.client.close()
                    except:
                        pass
                self.client = None
                self.mutex.unlock()
            for _ in range(100):
                if not self.running:
                    break
                self.msleep(50)

    def stop(self):
        self.running = False
        self.mutex.lock()
        if self.client:
            try:
                self.client.close()
            except:
                pass
        self.client = None
        self.mutex.unlock()
        self.wait()

# ==================== K线图窗口（增强版） ====================
class KLineDialog(QDialog):
    def __init__(self, symbol, reader, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.reader = reader
        self.setWindowTitle(f"{symbol} - 日K线图")
        self.setGeometry(200, 200, 1000, 800)

        self.full_df = None
        self.fund_df = None
        self.x_idx = None
        self.days = 60
        self.min_days = 10
        self.max_days = 500

        self.pan_start = None
        self.pan_xlim = None
        self.vline = None
        self.vline_ax = None

        layout = QVBoxLayout(self)

        self.figure = Figure(figsize=(10, 8), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.info_label = QLabel("鼠标移动显示完整数据 | 按 F11 全屏切换")
        layout.addWidget(self.info_label)
        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        self.load_data()
        self.update_plot()
        self.setFocusPolicy(Qt.StrongFocus)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.canvas.mpl_connect('axes_leave_event', self.on_mouse_leave)

    def load_data(self):
        try:
            df = self.reader.daily(symbol=self.symbol)
            if df is None or df.empty:
                self._show_error("无历史数据")
                return
            df = df.copy()
            if not isinstance(df.index, pd.DatetimeIndex):
                try:
                    df.index = pd.to_datetime(df.index)
                except:
                    df.index = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq='D')
            df = df.sort_index()

            rename_map = {
                'open': 'Open', 'high': 'High', 'low': 'Low',
                'close': 'Close', 'volume': 'Volume'
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            required = ['Open', 'High', 'Low', 'Close']
            missing = [c for c in required if c not in df.columns]
            if missing:
                self._show_error(f"缺少必要列: {missing}")
                return
            if 'Volume' not in df.columns:
                df['Volume'] = 0

            df = df[(df['Open'] > 0) & (df['High'] > 0) & (df['Low'] > 0) & (df['Close'] > 0)]
            if df.empty:
                self._show_error("清理后无有效数据")
                return

            self.x_idx = np.arange(len(df))
            self.full_df = df
            self.full_df['x_idx'] = self.x_idx
            self.full_df['MA5'] = self.full_df['Close'].rolling(5).mean()
            self.full_df['MA20'] = self.full_df['Close'].rolling(20).mean()

            self._load_fund_flow(df.index)

        except Exception as e:
            self._show_error(f"数据加载失败: {str(e)}")
            logger.error(traceback.format_exc())

    def _load_fund_flow(self, dates):
        try:
            market = 'sh' if self.symbol.startswith('6') else 'sz'
            symbol_full = f"{market}{self.symbol}"
            fund_df = ak.stock_individual_fund_flow(symbol=symbol_full)
            if fund_df is None or fund_df.empty:
                raise ValueError("无资金流向数据")
            fund_df = fund_df.rename(columns={'日期': 'date', '主力净流入-净额': 'main_net'})
            fund_df['date'] = pd.to_datetime(fund_df['date'])
            fund_df.set_index('date', inplace=True)
            self.fund_df = fund_df[['main_net']].reindex(dates).fillna(0)
            self.fund_df['x_idx'] = self.x_idx
            self.status_label.setText("已加载主力进出数据")
        except Exception as e:
            logger.warning(f"加载主力资金失败: {e}，使用模拟数据")
            np.random.seed(42)
            simulated = np.random.randn(len(self.full_df)) * 50000
            self.fund_df = pd.DataFrame({'main_net': simulated}, index=self.full_df.index)
            self.fund_df['x_idx'] = self.x_idx
            self.status_label.setText("主力进出数据（模拟）")

    def update_plot(self):
        if self.full_df is None or self.full_df.empty:
            return

        df_display = self.full_df.tail(self.days).copy()
        if len(df_display) < 2:
            self._show_error(f"数据量不足（仅{len(df_display)}条）")
            return

        fund_display = self.fund_df.iloc[-self.days:] if self.fund_df is not None else None

        self.figure.clear()
        gs = self.figure.add_gridspec(3, 1, height_ratios=[3, 1, 1], hspace=0.1)
        ax1 = self.figure.add_subplot(gs[0])
        ax2 = self.figure.add_subplot(gs[1], sharex=ax1)
        ax3 = self.figure.add_subplot(gs[2], sharex=ax1)

        x_vals = df_display['x_idx'].values

        self._draw_candlestick(ax1, df_display, x_vals)
        self._draw_volume(ax2, df_display, x_vals)
        self._draw_fund_flow(ax3, fund_display, x_vals)

        high_price = df_display['High'].max()
        low_price = df_display['Low'].min()
        ax1.axhline(high_price, color='red', linestyle='--', linewidth=1, alpha=0.7)
        ax1.axhline(low_price, color='green', linestyle='--', linewidth=1, alpha=0.7)
        ax1.text(x_vals[-1], high_price, f' 最高 {high_price:.2f}', va='bottom', fontsize=9, color='red')
        ax1.text(x_vals[-1], low_price, f' 最低 {low_price:.2f}', va='top', fontsize=9, color='green')

        step = max(1, len(x_vals) // 8)
        tick_positions = x_vals[::step]
        tick_labels = [date.strftime('%Y-%m-%d') for date in df_display.index[::step]]
        ax1.set_xticks(tick_positions)
        ax1.set_xticklabels(tick_labels, rotation=45, ha='right')
        ax1.set_xlim(x_vals[0], x_vals[-1])

        ax1.set_title(f'{self.symbol} 日K线 (最近{self.days}天)')
        ax1.set_ylabel('价格')
        ax2.set_ylabel('成交量')
        ax3.set_ylabel('主力净流入')
        ax3.set_xlabel('日期')

        self.figure.tight_layout()
        self.canvas.draw()
        self.status_label.setText(f"显示最近 {self.days} 天 | 共 {len(self.full_df)} 条数据")

    def _draw_candlestick(self, ax, df, x_vals):
        width = 0.6
        for x, row in zip(x_vals, df.itertuples()):
            open_price = row.Open
            high = row.High
            low = row.Low
            close = row.Close

            if close >= open_price:
                color = 'red'
                body_bottom = open_price
                body_height = close - open_price
            else:
                color = 'green'
                body_bottom = close
                body_height = open_price - close

            ax.plot([x, x], [low, high], color='black', linewidth=0.8)
            ax.bar(x, body_height, width, bottom=body_bottom, color=color, edgecolor='black')

        if 'MA5' in df.columns:
            ax.plot(x_vals, df['MA5'], label='MA5', linestyle='-', color='blue', linewidth=2)
        if 'MA20' in df.columns:
            ax.plot(x_vals, df['MA20'], label='MA20', linestyle='-', color='orange', linewidth=2)
        ax.legend()
        ax.grid(True, alpha=0.3)

    def _draw_volume(self, ax, df, x_vals):
        colors = ['red' if close >= open else 'green' for close, open in zip(df['Close'], df['Open'])]
        ax.bar(x_vals, df['Volume'], width=0.6, color=colors, alpha=0.7)
        ax.set_ylabel('成交量')
        ax.grid(True, alpha=0.3)

    def _draw_fund_flow(self, ax, fund_df, x_vals):
        if fund_df is None or fund_df.empty:
            ax.text(0.5, 0.5, '无主力进出数据', transform=ax.transAxes, ha='center')
            return
        net_flow = fund_df['main_net'].values
        colors = ['red' if x > 0 else 'green' for x in net_flow]
        ax.bar(x_vals, net_flow, width=0.6, color=colors, alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_ylabel('主力净流入')
        ax.grid(True, alpha=0.3)

    def _show_error(self, msg):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, msg, transform=ax.transAxes,
                ha='center', va='center', fontsize=12, color='red')
        self.canvas.draw()
        self.status_label.setText("错误: " + msg)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            self.days = min(self.days + 10, self.max_days)
            self.update_plot()
        elif event.key() == Qt.Key_Down:
            self.days = max(self.days - 10, self.min_days)
            self.update_plot()
        elif event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.info_label.setText("鼠标移动显示完整数据 | 按 F11 全屏切换")
        else:
            self.showFullScreen()
            self.info_label.setText("鼠标移动显示完整数据 | 按 F11 退出全屏")
        self.update_plot()

    def wheelEvent(self, event):
        if self.full_df is None or self.full_df.empty or self.x_idx is None:
            return
        ax = self.figure.axes[0] if self.figure.axes else None
        if ax is None:
            return
        try:
            xlim = ax.get_xlim()
            if not (isinstance(xlim[0], (int, float)) and isinstance(xlim[1], (int, float))):
                return
            center = (xlim[0] + xlim[1]) / 2.0
            delta = event.angleDelta().y()
            factor = 0.9 if delta > 0 else 1.1
            new_width = (xlim[1] - xlim[0]) * factor
            new_xlim = (center - new_width / 2, center + new_width / 2)

            data_min = self.x_idx[0]
            data_max = self.x_idx[-1]
            new_xlim = (max(new_xlim[0], data_min), min(new_xlim[1], data_max))
            if new_xlim[0] < new_xlim[1]:
                for ax in self.figure.axes:
                    ax.set_xlim(new_xlim)
                self.canvas.draw_idle()
        except Exception as e:
            pass

    def mousePressEvent(self, event):
        if self.full_df is None or self.full_df.empty:
            return
        if event.button() == Qt.LeftButton:
            self.pan_start = event.pos()
            ax = self.figure.axes[0] if self.figure.axes else None
            if ax:
                self.pan_xlim = ax.get_xlim()
            else:
                self.pan_xlim = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pan_start is not None and self.pan_xlim is not None and self.x_idx is not None:
            current_pos = event.pos()
            dx = current_pos.x() - self.pan_start.x()
            ax = self.figure.axes[0]
            xlim = ax.get_xlim()
            width_pixel = ax.bbox.width
            if width_pixel > 0:
                data_range = xlim[1] - xlim[0]
                shift = -dx / width_pixel * data_range
                new_xlim = (self.pan_xlim[0] + shift, self.pan_xlim[1] + shift)

                data_min = self.x_idx[0]
                data_max = self.x_idx[-1]
                new_xlim = (max(new_xlim[0], data_min), min(new_xlim[1], data_max))
                if new_xlim[0] < new_xlim[1]:
                    for ax in self.figure.axes:
                        ax.set_xlim(new_xlim)
                    self.canvas.draw_idle()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pan_start = None
            self.pan_xlim = None
        super().mouseReleaseEvent(event)

    def on_mouse_move(self, event):
        if event.inaxes and self.full_df is not None and not self.full_df.empty:
            ax = event.inaxes
            x = event.xdata
            y = event.ydata
            if x is not None and y is not None:
                idx = int(round(x))
                if 0 <= idx < len(self.full_df):
                    row = self.full_df.iloc[idx]
                    date = self.full_df.index[idx].strftime('%Y-%m-%d')
                    open_p = row['Open']
                    high = row['High']
                    low = row['Low']
                    close = row['Close']
                    volume = row['Volume']
                    main_net = self.fund_df.iloc[idx]['main_net'] if self.fund_df is not None else 0
                    info = (f"日期: {date}  O:{open_p:.2f}  H:{high:.2f}  L:{low:.2f}  C:{close:.2f}  "
                            f"成交量:{volume:.0f}  主力净流入:{main_net:+.2f}")
                    self.info_label.setText(info + " | 按 F11 全屏切换")
                    if ax == self.figure.axes[0]:
                        if self.vline is None or self.vline_ax != ax:
                            if self.vline is not None:
                                self.vline.remove()
                            self.vline = ax.axvline(x, color='gray', linestyle='--', linewidth=0.8, alpha=0.7)
                            self.vline_ax = ax
                        else:
                            self.vline.set_xdata([x, x])
                        self.canvas.draw_idle()
                    return
        if self.vline is not None:
            self.vline.remove()
            self.vline = None
            self.vline_ax = None
            self.canvas.draw_idle()
        self.info_label.setText("鼠标移动显示完整数据 | 按 F11 全屏切换")

    def on_mouse_leave(self, event):
        if self.vline is not None:
            self.vline.remove()
            self.vline = None
            self.vline_ax = None
            self.canvas.draw_idle()
        self.info_label.setText("鼠标移动显示完整数据 | 按 F11 全屏切换")

# ==================== 公共表格管理基类 ====================
class BaseStockTableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索代码或名称")
        self.search_edit.textChanged.connect(self.filter_stocks)
        toolbar.addWidget(QLabel("搜索:"))
        toolbar.addWidget(self.search_edit)

        self.refresh_btn = QPushButton("刷新行情")
        self.refresh_btn.clicked.connect(self.refresh_quotes)
        toolbar.addWidget(self.refresh_btn)

        self.add_btn = QPushButton("添加")
        self.add_btn.clicked.connect(self.add_stock)
        toolbar.addWidget(self.add_btn)

        self.del_btn = QPushButton("删除选中")
        self.del_btn.clicked.connect(self.del_stock)
        toolbar.addWidget(self.del_btn)

        self.import_btn = QPushButton("从CSV导入")
        self.import_btn.clicked.connect(self.import_csv)
        toolbar.addWidget(self.import_btn)

        self.export_btn = QPushButton("导出CSV")
        self.export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(self.export_btn)

        layout.addLayout(toolbar)

        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(5)
        self.stock_table.setHorizontalHeaderLabels(["代码", "名称", "细分行业", "现价", "涨速(手/分)"])
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stock_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.stock_table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.stock_table)

        btn_layout = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        self.status_bar = QStatusBar(self)
        layout.addWidget(self.status_bar)

    def load_data(self):
        raise NotImplementedError

    def filter_stocks(self):
        keyword = self.search_edit.text().strip().lower()
        for i in range(self.stock_table.rowCount()):
            code = self.stock_table.item(i, 0).text().lower()
            name = self.stock_table.item(i, 1).text().lower()
            visible = (keyword == "" or keyword in code or keyword in name)
            self.stock_table.setRowHidden(i, not visible)

    def refresh_quotes(self):
        if not self.parent:
            return
        latest_quotes = getattr(self.parent, 'latest_quotes', {})
        if not latest_quotes:
            self.status_bar.showMessage("暂无行情数据，请稍后手动刷新", 2000)
            return

        self.stock_table.setUpdatesEnabled(False)
        try:
            for i in range(self.stock_table.rowCount()):
                code_item = self.stock_table.item(i, 0)
                if code_item:
                    code = code_item.text()
                    quote = latest_quotes.get(code, {})
                    price = quote.get('price', '')
                    speed = quote.get('speed', '')
                    price_item = self.stock_table.item(i, 3)
                    speed_item = self.stock_table.item(i, 4)
                    if price_item:
                        price_item.setText(f"{price:.2f}" if price else "")
                    if speed_item:
                        speed_item.setText(f"{speed:.2f}" if speed else "")
        except Exception as e:
            self.status_bar.showMessage(f"刷新行情出错: {e}", 2000)
        finally:
            self.stock_table.setUpdatesEnabled(True)
            self.status_bar.showMessage("行情已刷新", 2000)

    def on_selection_changed(self):
        self.selected_symbols = set()
        for item in self.stock_table.selectedItems():
            row = item.row()
            code_item = self.stock_table.item(row, 0)
            if code_item:
                self.selected_symbols.add(code_item.text())

    def add_stock(self):
        raise NotImplementedError

    def del_stock(self):
        raise NotImplementedError

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                df = pd.read_csv(path, encoding='gbk')
                code_col = None
                for col in df.columns:
                    if '代码' in col or 'code' in col.lower():
                        code_col = col
                        break
                if code_col is None:
                    QMessageBox.warning(self, "错误", "未找到代码列")
                    return
                codes = df[code_col].astype(str).str.replace(r'\D', '', regex=True).tolist()
                self._add_codes(codes)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入失败: {e}")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                data = []
                for i in range(self.stock_table.rowCount()):
                    code = self.stock_table.item(i, 0).text()
                    name = self.stock_table.item(i, 1).text()
                    data.append([code, name])
                df = pd.DataFrame(data, columns=['代码', '名称'])
                df.to_csv(path, index=False, encoding='utf-8-sig')
                QMessageBox.information(self, "成功", f"导出至 {path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _add_codes(self, codes):
        raise NotImplementedError

# ==================== 自选股管理对话框 ====================
class FavoritesManagerDialog(BaseStockTableDialog):
    def __init__(self, favorites, name_map, sector_cache, parent=None):
        self.favorites = set(favorites)
        self.name_map = name_map
        self.sector_cache = sector_cache
        self.all_stocks = []
        self._prepare_all_stocks()
        super().__init__(parent)

    def _prepare_all_stocks(self):
        if self.parent and hasattr(self.parent, 'name_map') and self.parent.name_map:
            self.all_stocks = sorted(self.parent.name_map.items(), key=lambda x: x[0])
        else:
            try:
                stock_info = ak.stock_info_a_code_name()
                self.all_stocks = []
                for _, row in stock_info.iterrows():
                    code = row['code']
                    name = row['name']
                    if code.startswith(('sh', 'sz')):
                        code = code[2:]
                    self.all_stocks.append((code, name))
                self.all_stocks.sort(key=lambda x: x[0])
            except Exception as e:
                QMessageBox.critical(self, "错误", f"获取股票列表失败: {e}")
                self.all_stocks = []

    def load_data(self):
        self.stock_table.setUpdatesEnabled(False)
        self.stock_table.setRowCount(len(self.favorites))
        for i, code in enumerate(sorted(self.favorites)):
            name = self.name_map.get(code, "未知")
            industry = self.sector_cache.get(code, "未知")
            self.stock_table.setItem(i, 0, QTableWidgetItem(code))
            self.stock_table.setItem(i, 1, QTableWidgetItem(name))
            self.stock_table.setItem(i, 2, QTableWidgetItem(industry))
            self.stock_table.setItem(i, 3, QTableWidgetItem(""))
            self.stock_table.setItem(i, 4, QTableWidgetItem(""))
        self.stock_table.setSortingEnabled(True)
        self.stock_table.sortByColumn(0, Qt.AscendingOrder)
        self.stock_table.setUpdatesEnabled(True)
        QTimer.singleShot(100, self.refresh_quotes)

    def add_stock(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, QHBoxLayout, QLabel
        class SimpleStockPicker(QDialog):
            def __init__(self, all_stocks, current_favorites, parent=None):
                super().__init__(parent)
                self.setWindowTitle("选择股票")
                self.setGeometry(400, 300, 800, 500)
                self.all_stocks = all_stocks
                self.current_favorites = set(current_favorites)
                self.selected = []
                layout = QVBoxLayout(self)
                search_edit = QLineEdit()
                search_edit.setPlaceholderText("搜索代码或名称")
                search_edit.textChanged.connect(self.filter)
                layout.addWidget(search_edit)
                self.table = QTableWidget()
                self.table.setColumnCount(2)
                self.table.setHorizontalHeaderLabels(["代码", "名称"])
                self.table.setSelectionBehavior(QTableWidget.SelectRows)
                self.table.setSelectionMode(QTableWidget.MultiSelection)
                layout.addWidget(self.table)
                btn_layout = QHBoxLayout()
                ok_btn = QPushButton("确定")
                ok_btn.clicked.connect(self.accept)
                cancel_btn = QPushButton("取消")
                cancel_btn.clicked.connect(self.reject)
                btn_layout.addStretch()
                btn_layout.addWidget(ok_btn)
                btn_layout.addWidget(cancel_btn)
                layout.addLayout(btn_layout)
                self.load_data()
                self.search_edit = search_edit

            def load_data(self):
                self.table.setRowCount(len(self.all_stocks))
                for i, (code, name) in enumerate(self.all_stocks):
                    self.table.setItem(i, 0, QTableWidgetItem(code))
                    self.table.setItem(i, 1, QTableWidgetItem(name))
                    if code in self.current_favorites:
                        self.table.selectRow(i)
                self.table.setSortingEnabled(True)
                self.table.sortByColumn(0, Qt.AscendingOrder)

            def filter(self, text):
                keyword = text.strip().lower()
                for i in range(self.table.rowCount()):
                    code = self.table.item(i, 0).text().lower()
                    name = self.table.item(i, 1).text().lower()
                    visible = (keyword == "" or keyword in code or keyword in name)
                    self.table.setRowHidden(i, not visible)

            def get_selected(self):
                selected = set()
                for item in self.table.selectedItems():
                    row = item.row()
                    code = self.table.item(row, 0).text()
                    selected.add(code)
                return list(selected)

        picker = SimpleStockPicker(self.all_stocks, self.favorites, self)
        if picker.exec_() == QDialog.Accepted:
            new_codes = picker.get_selected()
            added = [c for c in new_codes if c not in self.favorites]
            if added:
                self._add_codes(added)
                self.status_bar.showMessage(f"已添加 {len(added)} 只股票", 2000)
            else:
                self.status_bar.showMessage("未添加新股票", 2000)

    def del_stock(self):
        if not self.selected_symbols:
            QMessageBox.warning(self, "提示", "请先选中要删除的股票")
            return
        reply = QMessageBox.question(self, "确认删除", f"确定删除 {len(self.selected_symbols)} 只自选股吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.favorites.difference_update(self.selected_symbols)
            self.save_changes()
            self.load_data()

    def _add_codes(self, codes):
        self.favorites.update(codes)
        self.save_changes()
        self.load_data()

    def save_changes(self):
        if self.parent:
            self.parent.favorites = list(self.favorites)
            if '自选股' not in self.parent.custom_groups:
                self.parent.custom_groups['自选股'] = []
            self.parent.custom_groups['自选股'] = list(self.favorites)
            self.parent.save_settings()
            self.parent.save_custom_groups()

# ==================== 板块管理对话框 ====================
class GroupManagerDialog(QDialog):
    def __init__(self, custom_groups, name_map, parent=None):
        super().__init__(parent)
        self.custom_groups = custom_groups
        self.name_map = name_map
        self.current_group = None
        self.setWindowTitle("板块管理")
        self.setGeometry(300, 300, 800, 500)

        layout = QHBoxLayout(self)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.group_list = QListWidget()
        self.group_list.itemClicked.connect(self.on_group_selected)
        left_layout.addWidget(QLabel("板块列表"))
        left_layout.addWidget(self.group_list)

        btn_add_group = QPushButton("新建板块")
        btn_add_group.clicked.connect(self.add_group)
        btn_del_group = QPushButton("删除板块")
        btn_del_group.clicked.connect(self.del_group)
        left_layout.addWidget(btn_add_group)
        left_layout.addWidget(btn_del_group)
        layout.addWidget(left_widget, 1)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(2)
        self.stock_table.setHorizontalHeaderLabels(["代码", "名称"])
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(QLabel("板块股票"))
        right_layout.addWidget(self.stock_table)

        btn_layout = QHBoxLayout()
        btn_add_stock = QPushButton("添加股票")
        btn_add_stock.clicked.connect(self.add_stock)
        btn_del_stock = QPushButton("删除选中")
        btn_del_stock.clicked.connect(self.del_stock)
        btn_import = QPushButton("从CSV导入")
        btn_import.clicked.connect(self.import_csv)
        btn_export = QPushButton("导出CSV")
        btn_export.clicked.connect(self.export_csv)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_add_stock)
        btn_layout.addWidget(btn_del_stock)
        btn_layout.addWidget(btn_import)
        btn_layout.addWidget(btn_export)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        right_layout.addLayout(btn_layout)

        layout.addWidget(right_widget, 2)

        self.refresh_group_list()
        if self.group_list.count() > 0:
            self.group_list.setCurrentRow(0)
            self.on_group_selected(self.group_list.item(0))

    def refresh_group_list(self):
        self.group_list.clear()
        for group in sorted(self.custom_groups.keys()):
            self.group_list.addItem(group)

    def on_group_selected(self, item):
        self.current_group = item.text()
        self.refresh_stock_table()

    def refresh_stock_table(self):
        if not self.current_group:
            return
        stocks = self.custom_groups.get(self.current_group, [])
        self.stock_table.setRowCount(len(stocks))
        for i, code in enumerate(stocks):
            name = self.name_map.get(code, "未知")
            self.stock_table.setItem(i, 0, QTableWidgetItem(code))
            self.stock_table.setItem(i, 1, QTableWidgetItem(name))

    def add_group(self):
        name, ok = QInputDialog.getText(self, "新建板块", "板块名称:")
        if ok and name and name not in self.custom_groups:
            self.custom_groups[name] = []
            self.refresh_group_list()
            self.save_changes()

    def del_group(self):
        if not self.current_group:
            return
        reply = QMessageBox.question(self, "确认删除", f"确定删除板块 '{self.current_group}' 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.custom_groups[self.current_group]
            self.current_group = None
            self.refresh_group_list()
            self.stock_table.setRowCount(0)
            self.save_changes()

    def add_stock(self):
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先选择一个板块")
            return
        code, ok = QInputDialog.getText(self, "添加股票", "输入股票代码（6位数字）:")
        if ok and code:
            code = code.strip()
            if code not in self.custom_groups[self.current_group]:
                self.custom_groups[self.current_group].append(code)
                self.refresh_stock_table()
                self.save_changes()

    def del_stock(self):
        if not self.current_group:
            return
        row = self.stock_table.currentRow()
        if row < 0:
            return
        code = self.stock_table.item(row, 0).text()
        self.custom_groups[self.current_group].remove(code)
        self.refresh_stock_table()
        self.save_changes()

    def import_csv(self):
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先选择一个板块")
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                df = pd.read_csv(path, header=None, names=['code', 'name'])
                codes = df['code'].astype(str).tolist()
                existing = set(self.custom_groups[self.current_group])
                new_codes = [c for c in codes if c not in existing]
                self.custom_groups[self.current_group].extend(new_codes)
                self.refresh_stock_table()
                self.save_changes()
                QMessageBox.information(self, "成功", f"导入 {len(new_codes)} 只股票")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入失败: {e}")

    def export_csv(self):
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先选择一个板块")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                stocks = self.custom_groups[self.current_group]
                data = []
                for code in stocks:
                    name = self.name_map.get(code, "未知")
                    data.append([code, name])
                df = pd.DataFrame(data, columns=['代码', '名称'])
                df.to_csv(path, index=False, encoding='utf-8-sig')
                QMessageBox.information(self, "成功", f"导出至 {path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def save_changes(self):
        if self.parent():
            self.parent().custom_groups = self.custom_groups
            self.parent().save_custom_groups()
            if '自选股' in self.custom_groups:
                self.parent().favorites = self.custom_groups['自选股'].copy()
                self.parent().save_settings()

# ==================== 股票选择对话框（支持分页） ====================
class StockSelectorDialog(QDialog):
    def __init__(self, current_symbols, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("选择监控股票")
        self.setGeometry(300, 200, 1000, 600)
        self.current_symbols = set(current_symbols)
        self.selected_symbols = set(current_symbols)
        self.all_stocks = []
        self.page_size = 200
        self.current_page = 0
        self.filtered_stocks = []
        self._prepare_stock_list()

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入代码或名称关键字")
        self.search_edit.textChanged.connect(self.filter_stocks)
        toolbar.addWidget(self.search_edit)

        self.refresh_btn = QPushButton("刷新行情")
        self.refresh_btn.clicked.connect(self.refresh_quotes)
        toolbar.addWidget(self.refresh_btn)

        self.page_label = QLabel()
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)
        toolbar.addStretch()
        toolbar.addWidget(self.page_label)
        toolbar.addWidget(self.prev_btn)
        toolbar.addWidget(self.next_btn)

        layout.addLayout(toolbar)

        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(5)
        self.stock_table.setHorizontalHeaderLabels(["代码", "名称", "细分行业", "现价", "涨速(手/分)"])
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stock_table.setSelectionMode(QTableWidget.MultiSelection)
        self.stock_table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.stock_table)

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.status_bar = QStatusBar(self)
        layout.addWidget(self.status_bar)

        self.load_stocks()

    def _prepare_stock_list(self):
        try:
            if self.parent and hasattr(self.parent, 'name_map') and self.parent.name_map:
                self.all_stocks = sorted(self.parent.name_map.items(), key=lambda x: x[0])
            else:
                stock_info = ak.stock_info_a_code_name()
                self.all_stocks = []
                for _, row in stock_info.iterrows():
                    code = row['code']
                    name = row['name']
                    if code.startswith(('sh', 'sz')):
                        code = code[2:]
                    self.all_stocks.append((code, name))
                self.all_stocks.sort(key=lambda x: x[0])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取股票列表失败: {e}")
            self.all_stocks = []

    def load_stocks(self):
        self.filtered_stocks = self.all_stocks
        self.current_page = 0
        self.update_table()

    def filter_stocks(self):
        keyword = self.search_edit.text().strip().lower()
        if keyword:
            self.filtered_stocks = [(code, name) for code, name in self.all_stocks if
                                    keyword in code.lower() or keyword in name.lower()]
        else:
            self.filtered_stocks = self.all_stocks
        self.current_page = 0
        self.update_table()

    def update_table(self):
        start = self.current_page * self.page_size
        end = min(start + self.page_size, len(self.filtered_stocks))
        page_stocks = self.filtered_stocks[start:end]
        self.stock_table.setRowCount(len(page_stocks))
        for i, (code, name) in enumerate(page_stocks):
            self.stock_table.setItem(i, 0, QTableWidgetItem(code))
            self.stock_table.setItem(i, 1, QTableWidgetItem(name))
            industry = "未知"
            if self.parent and hasattr(self.parent, 'sector_cache'):
                industry = self.parent.sector_cache.get(code, "未知")
            self.stock_table.setItem(i, 2, QTableWidgetItem(industry))
            self.stock_table.setItem(i, 3, QTableWidgetItem(""))
            self.stock_table.setItem(i, 4, QTableWidgetItem(""))
            if code in self.current_symbols:
                self.stock_table.selectRow(i)
        self.page_label.setText(
            f"第 {self.current_page + 1} / {max(1, (len(self.filtered_stocks) + self.page_size - 1) // self.page_size)} 页")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(end < len(self.filtered_stocks))
        QTimer.singleShot(100, self.refresh_quotes)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_table()

    def next_page(self):
        if (self.current_page + 1) * self.page_size < len(self.filtered_stocks):
            self.current_page += 1
            self.update_table()

    def refresh_quotes(self):
        if not self.parent:
            return
        latest_quotes = getattr(self.parent, 'latest_quotes', {})
        if not latest_quotes:
            self.status_bar.showMessage("暂无行情数据，请稍后手动刷新", 2000)
            return
        self.stock_table.setUpdatesEnabled(False)
        try:
            for i in range(self.stock_table.rowCount()):
                code_item = self.stock_table.item(i, 0)
                if code_item:
                    code = code_item.text()
                    quote = latest_quotes.get(code, {})
                    price = quote.get('price', '')
                    speed = quote.get('speed', '')
                    price_item = self.stock_table.item(i, 3)
                    speed_item = self.stock_table.item(i, 4)
                    if price_item:
                        price_item.setText(f"{price:.2f}" if price else "")
                    if speed_item:
                        speed_item.setText(f"{speed:.2f}" if speed else "")
        except Exception as e:
            self.status_bar.showMessage(f"刷新行情出错: {e}", 2000)
        finally:
            self.stock_table.setUpdatesEnabled(True)
            self.status_bar.showMessage("行情已刷新", 2000)

    def on_selection_changed(self):
        selected_rows = set(item.row() for item in self.stock_table.selectedItems())
        self.selected_symbols = set()
        for row in selected_rows:
            code_item = self.stock_table.item(row, 0)
            if code_item:
                self.selected_symbols.add(code_item.text())

    def get_selected_symbols(self):
        return list(self.selected_symbols)

# ==================== 回测工作线程 ====================
class BacktestWorker(QThread):
    progress = pyqtSignal(int)
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, strategy_file, symbol, capital, commission, slippage, tdx_dir, optimize=False, param_space=None):
        super().__init__()
        self.strategy_file = strategy_file
        self.symbol = symbol
        self.capital = capital
        self.commission = commission
        self.slippage = slippage
        self.optimize = optimize
        self.param_space = param_space or {}
        self.tdx_dir = tdx_dir
        self.data = None
        self.reader = None

    def run(self):
        try:
            self.reader = Reader.factory(market='std', tdxdir=self.tdx_dir)
            spec = importlib.util.spec_from_file_location("strategy_module", self.strategy_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            strategy_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and name != 'BaseStrategy':
                    strategy_class = obj
                    break
            if strategy_class is None:
                self.error_occurred.emit("未找到策略类")
                return

            df = self.reader.daily(symbol=self.symbol)
            if df.empty:
                self.error_occurred.emit("无历史数据")
                return
            df = df.sort_index()
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})

            engine = BacktestEngine(strategy_class, self.commission, self.slippage)

            self.progress.emit(10)

            if self.optimize:
                if not SKOPT_AVAILABLE:
                    self.error_occurred.emit("scikit-optimize未安装，无法进行优化")
                    return
                best_params, best_sharpe = engine.optimize(df, self.param_space, n_calls=30,
                                                           initial_capital=self.capital)
                self.progress.emit(80)
                result = engine.run(df, self.capital, **best_params)
                result['best_params'] = best_params
                result['best_sharpe'] = best_sharpe
            else:
                result = engine.run(df, self.capital)

            self.progress.emit(100)
            self.result_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))

# ==================== 新增自动驾驶独立对话框 ====================
class RLTraderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("强化学习执行器")
        self.setGeometry(400, 300, 600, 500)
        self.model_path = ""
        self.rl_trader = None

        layout = QVBoxLayout(self)

        self.status_label = QLabel("状态：未加载模型")
        layout.addWidget(self.status_label)

        file_layout = QHBoxLayout()
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setPlaceholderText("选择模型文件(.zip)")
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self.browse_model)
        file_layout.addWidget(self.model_path_edit)
        file_layout.addWidget(self.browse_btn)
        layout.addLayout(file_layout)

        self.load_btn = QPushButton("加载模型")
        self.load_btn.clicked.connect(self.load_model)
        layout.addWidget(self.load_btn)

        group = QGroupBox("训练新模型")
        group_layout = QFormLayout(group)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(parent.symbols if parent else [])
        group_layout.addRow("股票代码:", self.symbol_combo)

        self.total_volume = QDoubleSpinBox()
        self.total_volume.setRange(1000, 1000000)
        self.total_volume.setValue(10000)
        group_layout.addRow("总成交量(股):", self.total_volume)

        self.train_btn = QPushButton("开始训练")
        self.train_btn.clicked.connect(self.train_model)
        group_layout.addRow(self.train_btn)

        self.progress = QProgressBar()
        group_layout.addRow(self.progress)

        layout.addWidget(group)

        test_group = QGroupBox("模拟执行")
        test_layout = QFormLayout(test_group)
        self.test_volume = QDoubleSpinBox()
        self.test_volume.setRange(1000, 1000000)
        self.test_volume.setValue(10000)
        test_layout.addRow("订单量(股):", self.test_volume)

        self.execute_btn = QPushButton("模拟执行")
        self.execute_btn.clicked.connect(self.simulate_execute)
        test_layout.addRow(self.execute_btn)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        test_layout.addRow(self.result_text)

        layout.addWidget(test_group)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self.setLayout(layout)

    def browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择模型文件", "", "Zip files (*.zip)")
        if path:
            self.model_path_edit.setText(path)

    def load_model(self):
        path = self.model_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择模型文件")
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "错误", "文件不存在")
            return
        try:
            self.rl_trader = RLTrader(path)
            self.status_label.setText(f"状态：已加载模型 {os.path.basename(path)}")
            self.result_text.append(f"模型加载成功: {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败: {e}")

    def train_model(self):
        if not RL_AVAILABLE:
            QMessageBox.critical(self, "错误", "强化学习库未安装")
            return
        symbol = self.symbol_combo.currentText()
        volume = self.total_volume.value()
        data = self.parent.get_latest_data().get(symbol)
        if data is None or data.empty:
            QMessageBox.warning(self, "错误", "无法获取历史数据")
            return
        try:
            self.train_btn.setEnabled(False)
            self.progress.setValue(10)
            price_model = SimplePriceImpact()
            rl = RLTrader()
            # 计算波动率列
            data['volatility'] = data['close'].pct_change().rolling(20).std().fillna(0)
            rl.train(data, volume, price_model, total_timesteps=10000)
            self.progress.setValue(100)
            save_path = QFileDialog.getSaveFileName(self, "保存模型", "", "Zip files (*.zip)")[0]
            if save_path:
                if not save_path.endswith('.zip'):
                    save_path += '.zip'
                rl.model.save(save_path)
                self.model_path_edit.setText(save_path)
                self.result_text.append(f"模型已保存至 {save_path}")
                self.status_label.setText("状态：模型已训练并保存")
            self.train_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"训练失败: {e}")
            self.train_btn.setEnabled(True)

    def simulate_execute(self):
        if self.rl_trader is None:
            QMessageBox.warning(self, "提示", "请先加载模型")
            return
        symbol = self.symbol_combo.currentText()
        volume = self.test_volume.value()
        data = self.parent.get_latest_data().get(symbol)
        if data is None or data.empty:
            QMessageBox.warning(self, "错误", "无法获取历史数据")
            return
        try:
            price_model = SimplePriceImpact()
            # 添加波动率列
            data['volatility'] = data['close'].pct_change().rolling(20).std().fillna(0)
            trades = self.rl_trader.execute(data, volume, price_model)
            self.result_text.append(f"执行结果：共 {len(trades)} 笔成交")
            total_cost = sum(t['price'] * t['volume'] for t in trades)
            self.result_text.append(f"总成本: {total_cost:.2f}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"执行失败: {e}")

class GANStressTesterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("GAN压力测试器")
        self.setGeometry(400, 300, 600, 500)
        self.generator = None
        self.stress_tester = None

        layout = QVBoxLayout(self)

        self.status_label = QLabel("状态：未训练")
        layout.addWidget(self.status_label)

        group = QGroupBox("训练GAN模型")
        group_layout = QFormLayout(group)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(parent.symbols if parent else [])
        group_layout.addRow("股票代码:", self.symbol_combo)

        self.epochs = QSpinBox()
        self.epochs.setRange(100, 10000)
        self.epochs.setValue(1000)
        group_layout.addRow("训练轮数:", self.epochs)

        self.train_btn = QPushButton("开始训练")
        self.train_btn.clicked.connect(self.train_model)
        group_layout.addRow(self.train_btn)

        self.progress = QProgressBar()
        group_layout.addRow(self.progress)

        layout.addWidget(group)

        test_group = QGroupBox("压力测试")
        test_layout = QFormLayout(test_group)

        self.scenarios_num = QSpinBox()
        self.scenarios_num.setRange(100, 10000)
        self.scenarios_num.setValue(1000)
        test_layout.addRow("生成场景数量:", self.scenarios_num)

        self.generate_btn = QPushButton("生成场景")
        self.generate_btn.clicked.connect(self.generate_scenarios)
        test_layout.addRow(self.generate_btn)

        self.portfolio_weights = QLineEdit()
        self.portfolio_weights.setPlaceholderText("例如: 600519:0.5,000001:0.5")
        test_layout.addRow("组合权重:", self.portfolio_weights)

        self.stress_btn = QPushButton("压力测试")
        self.stress_btn.clicked.connect(self.stress_test)
        test_layout.addRow(self.stress_btn)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        test_layout.addRow(self.result_text)

        layout.addWidget(test_group)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self.setLayout(layout)

    def train_model(self):
        if not TORCH_AVAILABLE:
            QMessageBox.critical(self, "错误", "PyTorch未安装")
            return
        symbol = self.symbol_combo.currentText()
        data = self.parent.get_latest_data().get(symbol)
        if data is None or data.empty:
            QMessageBox.warning(self, "错误", "无法获取历史数据")
            return
        returns = data['close'].pct_change().dropna().values
        if len(returns) < 100:
            QMessageBox.warning(self, "错误", "历史数据不足")
            return
        try:
            self.train_btn.setEnabled(False)
            self.progress.setValue(10)
            self.stress_tester = GANStressTester()
            self.stress_tester.train(returns, epochs=self.epochs.value())
            self.progress.setValue(100)
            self.status_label.setText("状态：模型已训练")
            self.result_text.append("GAN模型训练完成")
            self.train_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"训练失败: {e}")
            self.train_btn.setEnabled(True)

    def generate_scenarios(self):
        if self.stress_tester is None:
            QMessageBox.warning(self, "提示", "请先训练模型")
            return
        n = self.scenarios_num.value()
        scenarios = self.stress_tester.generate_scenarios(n_scenarios=n, seq_length=100)
        self.result_text.append(f"已生成 {n} 个情景，形状: {scenarios.shape}")

    def stress_test(self):
        if self.stress_tester is None:
            QMessageBox.warning(self, "提示", "请先训练模型")
            return
        weights_text = self.portfolio_weights.text().strip()
        if not weights_text:
            QMessageBox.warning(self, "提示", "请输入组合权重")
            return
        try:
            weights = {}
            for item in weights_text.split(','):
                k, v = item.split(':')
                weights[k.strip()] = float(v.strip())
            data_dict = self.parent.get_latest_data()
            portfolio_returns = None
            for sym, weight in weights.items():
                df = data_dict.get(sym)
                if df is None:
                    continue
                ret = df['close'].pct_change().fillna(0)
                if portfolio_returns is None:
                    portfolio_returns = ret * weight
                else:
                    portfolio_returns += ret * weight
            if portfolio_returns is None:
                QMessageBox.warning(self, "错误", "无法计算组合收益率")
                return
            scenarios = self.stress_tester.generate_scenarios(n_scenarios=1000, seq_length=len(portfolio_returns))
            max_dd = self.stress_tester.stress_test(portfolio_returns.values, scenarios)
            self.result_text.append(f"压力测试最大回撤: {max_dd:.2%}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"压力测试失败: {e}")

class PortfolioOptimizerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("动态组合配置器")
        self.setGeometry(400, 300, 700, 600)

        layout = QVBoxLayout(self)

        group1 = QGroupBox("股票池")
        group1_layout = QVBoxLayout(group1)
        self.stock_list = QListWidget()
        self.stock_list.setSelectionMode(QListWidget.MultiSelection)
        self.stock_list.addItems(parent.symbols if parent else [])
        group1_layout.addWidget(self.stock_list)
        layout.addWidget(group1)

        group2 = QGroupBox("优化参数")
        form = QFormLayout(group2)

        self.target_return = QDoubleSpinBox()
        self.target_return.setRange(-100, 100)
        self.target_return.setValue(15)
        self.target_return.setSuffix("%")
        form.addRow("目标年化收益:", self.target_return)

        self.risk_free = QDoubleSpinBox()
        self.risk_free.setRange(0, 10)
        self.risk_free.setValue(2)
        self.risk_free.setSuffix("%")
        form.addRow("无风险利率:", self.risk_free)

        self.method = QComboBox()
        self.method.addItems(["均值-方差", "风险平价", "Black-Litterman"])
        form.addRow("优化方法:", self.method)

        self.max_weight = QDoubleSpinBox()
        self.max_weight.setRange(0.1, 1.0)
        self.max_weight.setValue(0.3)
        form.addRow("单资产最大权重:", self.max_weight)

        layout.addWidget(group2)

        self.optimize_btn = QPushButton("运行优化")
        self.optimize_btn.clicked.connect(self.run_optimization)
        layout.addWidget(self.optimize_btn)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(QLabel("优化结果:"))
        layout.addWidget(self.result_text)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self.setLayout(layout)

    def run_optimization(self):
        if not CVXPY_AVAILABLE:
            QMessageBox.critical(self, "错误", "cvxpy未安装")
            return
        selected_items = self.stock_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请选择至少一只股票")
            return
        symbols = [item.text() for item in selected_items]
        data_dict = self.parent.get_latest_data()
        returns_data = {}
        for sym in symbols:
            df = data_dict.get(sym)
            if df is not None and not df.empty:
                returns_data[sym] = df['close'].pct_change().dropna()
        if len(returns_data) < 2:
            QMessageBox.warning(self, "错误", "数据不足，至少需要两只股票")
            return
        df_returns = pd.DataFrame(returns_data).dropna()
        if df_returns.empty:
            QMessageBox.warning(self, "错误", "数据对齐后为空")
            return
        expected_returns = df_returns.mean() * 252
        cov_matrix = df_returns.cov() * 252

        optimizer = PortfolioOptimizer(expected_returns, cov_matrix, self.risk_free.value()/100)
        target = self.target_return.value() / 100

        try:
            if self.method.currentText() == "均值-方差":
                weights = optimizer.mean_variance(target, self.max_weight.value())
            elif self.method.currentText() == "风险平价":
                weights = optimizer.risk_parity()
            else:
                views = np.ones((1, len(symbols)))
                confidences = np.array([0.1])
                mu_bl = optimizer.black_litterman(views, confidences)
                optimizer.expected_returns = mu_bl
                weights = optimizer.mean_variance(target, self.max_weight.value())

            if weights is None:
                self.result_text.append("优化失败，请检查约束条件")
                return

            self.result_text.clear()
            self.result_text.append("优化结果：")
            for sym, w in zip(symbols, weights):
                self.result_text.append(f"{sym}: {w:.4f}")
            port_return = np.dot(expected_returns, weights)
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            self.result_text.append(f"\n组合预期年化收益: {port_return:.2%}")
            self.result_text.append(f"组合年化波动率: {port_vol:.2%}")
            self.result_text.append(f"夏普比率: {(port_return - self.risk_free.value()/100) / port_vol:.4f}")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"优化失败: {e}")

class AutoPilotControlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("自动驾驶引擎")
        self.setGeometry(400, 300, 700, 600)
        self.engine = None

        layout = QVBoxLayout(self)

        group = QGroupBox("引擎设置")
        form = QFormLayout(group)

        self.target_return = QDoubleSpinBox()
        self.target_return.setRange(-100, 100)
        self.target_return.setValue(15.0)
        self.target_return.setSuffix("%")
        form.addRow("目标年化收益:", self.target_return)

        self.max_drawdown = QDoubleSpinBox()
        self.max_drawdown.setRange(1, 50)
        self.max_drawdown.setValue(20)
        self.max_drawdown.setSuffix("%")
        form.addRow("最大回撤容忍度:", self.max_drawdown)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.5, 24)
        self.interval.setValue(1.0)
        self.interval.setSuffix("小时")
        form.addRow("调仓间隔:", self.interval)

        self.use_rl = QCheckBox("使用强化学习执行器")
        self.use_rl.setChecked(RL_AVAILABLE)
        self.use_rl.setEnabled(RL_AVAILABLE)
        self.rl_model_path = QLineEdit()
        self.rl_model_path.setPlaceholderText("RL模型路径(.zip)")
        self.browse_rl_btn = QPushButton("浏览")
        self.browse_rl_btn.clicked.connect(lambda: self.browse_file(self.rl_model_path))
        rl_layout = QHBoxLayout()
        rl_layout.addWidget(self.rl_model_path)
        rl_layout.addWidget(self.browse_rl_btn)
        form.addRow(self.use_rl)
        form.addRow("RL模型文件:", rl_layout)

        self.use_gan = QCheckBox("使用GAN压力测试")
        self.use_gan.setChecked(TORCH_AVAILABLE)
        self.use_gan.setEnabled(TORCH_AVAILABLE)
        form.addRow(self.use_gan)

        layout.addWidget(group)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动自动驾驶")
        self.start_btn.clicked.connect(self.start_engine)
        self.stop_btn = QPushButton("停止自动驾驶")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_engine)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        layout.addWidget(QLabel("运行日志:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

        self.setLayout(layout)

    def browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, "选择模型文件", "", "Zip files (*.zip)")
        if path:
            line_edit.setText(path)

    def start_engine(self):
        if self.engine and self.engine.isRunning():
            QMessageBox.warning(self, "提示", "引擎已在运行")
            return

        if self.use_rl.isChecked() and not RL_AVAILABLE:
            QMessageBox.critical(self, "错误", "强化学习执行需要安装 stable-baselines3")
            return
        if self.use_gan.isChecked() and not TORCH_AVAILABLE:
            QMessageBox.critical(self, "错误", "GAN压力测试需要安装 PyTorch")
            return
        if not CVXPY_AVAILABLE:
            QMessageBox.critical(self, "错误", "组合优化需要安装 cvxpy")
            return

        data = self.parent.get_latest_data()
        if not data:
            QMessageBox.warning(self, "警告", "无法获取历史数据，请等待数据加载")
            return

        rl_trader = None
        if self.use_rl.isChecked():
            model_path = self.rl_model_path.text().strip()
            if model_path and os.path.exists(model_path):
                rl_trader = RLTrader(model_path)
            else:
                QMessageBox.warning(self, "警告", f"模型文件 {model_path} 不存在，将不使用RL执行器")

        stress_tester = None
        if self.use_gan.isChecked():
            stress_tester = GANStressTester() if TORCH_AVAILABLE else None

        returns_df = pd.DataFrame()
        for sym, df in data.items():
            if df is not None and not df.empty:
                returns_df[sym] = df['close'].pct_change()
        returns_df = returns_df.dropna()
        if returns_df.empty:
            QMessageBox.warning(self, "错误", "无法计算收益率")
            return
        expected_returns = returns_df.mean() * 252
        cov_matrix = returns_df.cov() * 252
        optimizer = PortfolioOptimizer(expected_returns, cov_matrix)

        portfolio = self.parent.get_current_positions()

        manager = AutoPortfolioManager(optimizer, rl_trader, stress_tester,
                                       self.target_return.value(), self.max_drawdown.value())

        self.engine = AutoPilotEngine(manager, portfolio, self.parent, self.interval.value() * 3600)
        self.engine.status_signal.connect(self.log_text.append)
        self.engine.order_signal.connect(lambda x: self.log_text.append(str(x)))
        self.engine.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_text.append("自动驾驶已启动")

    def stop_engine(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_text.append("自动驾驶已停止")

# ==================== 主窗口 ====================
class QuantMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("通达信量化监控系统 - 自动驾驶增强版")
        self.setGeometry(100, 100, 1500, 800)

        self.settings = QSettings('QuantMonitor', 'QuantMonitor')

        self.latest_quotes = {}
        self.signals = {}
        self.historical_data = {}
        self.sector_cache = {}
        self.name_map = {}
        self.last_data = {}
        self.reader = None
        self.data_thread = None
        self.tray_icon = None
        self.log_widget = None
        self.preview_figure = None
        self.preview_canvas = None
        self.current_preview_symbol = None
        self.custom_groups = {}

        self.auto_factor_miner = AutoFactorMiner()
        self.ai_strategy_gen = None
        self.backtest_engine = None
        self.risk_manager = RiskManager(initial_capital=1e6)

        self.load_settings()

        self._init_ui()
        self._init_log_dock()
        self._init_tray()

        self.reader = Reader.factory(market='std', tdxdir=self.tdx_dir)
        self._init_name_map()
        self._init_technical_indicators()
        self._refresh_sector_cache()

        self._show_historical_data()
        self._start_data_thread()

        self.sector_timer = QTimer()
        self.sector_timer.timeout.connect(self._refresh_sector_cache)
        self.sector_timer.start(self.sector_refresh_interval)

        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)

    # 辅助方法：显示各种对话框
    def show_rl_trader_dialog(self):
        dialog = RLTraderDialog(self)
        dialog.exec_()

    def show_gan_tester_dialog(self):
        dialog = GANStressTesterDialog(self)
        dialog.exec_()

    def show_portfolio_optimizer_dialog(self):
        dialog = PortfolioOptimizerDialog(self)
        dialog.exec_()

    def show_autopilot_control_dialog(self):
        dialog = AutoPilotControlDialog(self)
        dialog.exec_()

    def load_settings(self):
        self.tdx_dir = self.settings.value('tdx_dir', DEFAULT_SETTINGS['tdx_dir'])
        symbols_str = self.settings.value('symbols', json.dumps(DEFAULT_SETTINGS['symbols']))
        self.symbols = json.loads(symbols_str)
        self.ma_short = int(self.settings.value('ma_short', DEFAULT_SETTINGS['ma_short']))
        self.ma_long = int(self.settings.value('ma_long', DEFAULT_SETTINGS['ma_long']))
        self.host = self.settings.value('host', DEFAULT_SETTINGS['host'])
        self.port = int(self.settings.value('port', DEFAULT_SETTINGS['port']))
        self.refresh_interval = int(self.settings.value('refresh_interval', DEFAULT_SETTINGS['refresh_interval']))
        self.sector_refresh_interval = int(
            self.settings.value('sector_refresh_interval', DEFAULT_SETTINGS['sector_refresh_interval']))
        self.show_macd = self.settings.value('show_macd', DEFAULT_SETTINGS['show_macd'], type=bool)
        self.show_rsi = self.settings.value('show_rsi', DEFAULT_SETTINGS['show_rsi'], type=bool)
        self.show_kdj = self.settings.value('show_kdj', DEFAULT_SETTINGS['show_kdj'], type=bool)
        self.show_boll = self.settings.value('show_boll', DEFAULT_SETTINGS['show_boll'], type=bool)
        self.enable_notify = self.settings.value('enable_notify', DEFAULT_SETTINGS['enable_notify'], type=bool)
        fav_str = self.settings.value('favorites', json.dumps(DEFAULT_SETTINGS['favorites']))
        self.favorites = json.loads(fav_str)
        alerts_str = self.settings.value('alerts', json.dumps(DEFAULT_SETTINGS['alerts']))
        self.alerts = json.loads(alerts_str)

        groups_str = self.settings.value('custom_groups', '{}')
        self.custom_groups = json.loads(groups_str)
        if '自选股' not in self.custom_groups:
            self.custom_groups['自选股'] = self.favorites.copy()
        else:
            self.favorites = self.custom_groups['自选股'].copy()
        self.save_custom_groups()

        self.risk_manager.stop_loss_mult = float(
            self.settings.value('risk_stop_mult', DEFAULT_SETTINGS['risk_stop_mult']))
        self.risk_manager.risk_per_trade = float(
            self.settings.value('risk_per_trade', DEFAULT_SETTINGS['risk_per_trade']))
        self.risk_manager.use_gnn = self.settings.value('risk_use_gnn', DEFAULT_SETTINGS['risk_use_gnn'], type=bool)
        self.commission = float(self.settings.value('commission', DEFAULT_SETTINGS['commission']))
        self.slippage = float(self.settings.value('slippage', DEFAULT_SETTINGS['slippage']))

    def save_settings(self):
        self.settings.setValue('tdx_dir', self.tdx_dir)
        self.settings.setValue('symbols', json.dumps(self.symbols))
        self.settings.setValue('ma_short', self.ma_short)
        self.settings.setValue('ma_long', self.ma_long)
        self.settings.setValue('host', self.host)
        self.settings.setValue('port', self.port)
        self.settings.setValue('refresh_interval', self.refresh_interval)
        self.settings.setValue('sector_refresh_interval', self.sector_refresh_interval)
        self.settings.setValue('show_macd', self.show_macd)
        self.settings.setValue('show_rsi', self.show_rsi)
        self.settings.setValue('show_kdj', self.show_kdj)
        self.settings.setValue('show_boll', self.show_boll)
        self.settings.setValue('enable_notify', self.enable_notify)
        self.settings.setValue('favorites', json.dumps(self.favorites))
        self.settings.setValue('alerts', json.dumps(self.alerts))
        self.settings.setValue('risk_stop_mult', self.risk_manager.stop_loss_mult)
        self.settings.setValue('risk_per_trade', self.risk_manager.risk_per_trade)
        self.settings.setValue('risk_use_gnn', self.risk_manager.use_gnn)
        self.settings.setValue('commission', self.commission)
        self.settings.setValue('slippage', self.slippage)
        self.save_custom_groups()

    def save_custom_groups(self):
        self.settings.setValue('custom_groups', json.dumps(self.custom_groups))

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        refresh_btn = QAction("刷新数据", self)
        refresh_btn.triggered.connect(self.manual_refresh)
        toolbar.addAction(refresh_btn)

        config_btn = QAction("配置", self)
        config_btn.triggered.connect(self.show_config_dialog)
        toolbar.addAction(config_btn)

        export_btn = QAction("导出数据", self)
        export_btn.triggered.connect(self.export_data)
        toolbar.addAction(export_btn)

        clear_log_btn = QAction("清空日志", self)
        clear_log_btn.triggered.connect(lambda: self.log_widget.clear())
        toolbar.addAction(clear_log_btn)

        self.table = QTableWidget()
        self.update_table_headers()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table.currentCellChanged.connect(self.on_current_cell_changed)
        left_layout.addWidget(self.table)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        preview_label = QLabel("K线预览 (点击表格行)")
        preview_label.setAlignment(Qt.AlignCenter)
        self.preview_figure = Figure(figsize=(5, 4), dpi=80)
        self.preview_canvas = FigureCanvas(self.preview_figure)
        self.preview_toolbar = NavigationToolbar(self.preview_canvas, self)
        right_layout.addWidget(preview_label)
        right_layout.addWidget(self.preview_toolbar)
        right_layout.addWidget(self.preview_canvas)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        self.status_info = QLabel("")
        self.status_bar.addPermanentWidget(self.status_info)

        menubar = self.menuBar()
        config_menu = menubar.addMenu('配置')
        save_action = QAction('保存配置', self)
        save_action.triggered.connect(self.save_settings)
        config_menu.addAction(save_action)
        edit_symbols_action = QAction('编辑监控股票', self)
        edit_symbols_action.triggered.connect(self.edit_symbols)
        config_menu.addAction(edit_symbols_action)
        indicator_action = QAction('指标设置', self)
        indicator_action.triggered.connect(self.edit_indicators)
        config_menu.addAction(indicator_action)

        alert_menu = menubar.addMenu('预警')
        add_alert_action = QAction('添加预警', self)
        add_alert_action.triggered.connect(self.add_alert)
        clear_alerts_action = QAction('清空预警', self)
        clear_alerts_action.triggered.connect(self.clear_alerts)
        alert_menu.addAction(add_alert_action)
        alert_menu.addAction(clear_alerts_action)

        group_menu = menubar.addMenu('板块管理')
        manage_action = QAction('管理板块', self)
        manage_action.triggered.connect(self.open_group_manager)
        group_menu.addAction(manage_action)
        import_tdx_action = QAction('从通达信导入自选股(CSV)', self)
        import_tdx_action.triggered.connect(self.import_from_tdx_csv)
        group_menu.addAction(import_tdx_action)

        fav_menu = menubar.addMenu('自选股')
        show_fav_action = QAction('显示自选股', self)
        show_fav_action.triggered.connect(self.show_favorites)
        fav_menu.addAction(show_fav_action)

        ai_menu = menubar.addMenu('AI工具')
        factor_action = QAction('自动因子挖掘', self)
        factor_action.triggered.connect(self.show_ai_factor_dialog)
        strategy_action = QAction('AI策略生成', self)
        strategy_action.triggered.connect(self.show_ai_strategy_dialog)
        backtest_action = QAction('回测与优化', self)
        backtest_action.triggered.connect(self.show_backtest_dialog)
        risk_action = QAction('智能风控设置', self)
        risk_action.triggered.connect(self.show_risk_dialog)
        ai_menu.addAction(factor_action)
        ai_menu.addAction(strategy_action)
        ai_menu.addAction(backtest_action)
        ai_menu.addAction(risk_action)

        autopilot_menu = menubar.addMenu('自动驾驶')
        autopilot_action = QAction('设置自动驾驶', self)
        autopilot_action.triggered.connect(self.show_autopilot_dialog)
        autopilot_menu.addAction(autopilot_action)
        rl_action = QAction('强化学习执行器', self)
        rl_action.triggered.connect(self.show_rl_trader_dialog)
        autopilot_menu.addAction(rl_action)
        gan_action = QAction('GAN压力测试器', self)
        gan_action.triggered.connect(self.show_gan_tester_dialog)
        autopilot_menu.addAction(gan_action)
        portfolio_action = QAction('动态组合配置器', self)
        portfolio_action.triggered.connect(self.show_portfolio_optimizer_dialog)
        autopilot_menu.addAction(portfolio_action)
        engine_action = QAction('自动驾驶引擎', self)
        engine_action.triggered.connect(self.show_autopilot_control_dialog)
        autopilot_menu.addAction(engine_action)

    def update_table_headers(self):
        headers = ["代码", "名称", "细分行业", "最新价", "涨跌幅%", "涨速(手/分)",
                   f"MA{self.ma_short}", f"MA{self.ma_long}"]
        if self.show_macd:
            headers.append("MACD")
        if self.show_rsi:
            headers.append("RSI")
        if self.show_kdj:
            headers.append("KDJ_K")
        if self.show_boll:
            headers.append("BOLL宽度")
        headers.extend(["信号", "数据状态", "更新时间"])
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

    def _init_log_dock(self):
        self.log_dock = QDockWidget("运行日志", self)
        self.log_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)

    def log(self, msg):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_widget.append(f"[{timestamp}] {msg}")
        self.log_widget.ensureCursorVisible()
        logger.info(msg)

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon())
        self.tray_icon.setVisible(True)

    def _init_name_map(self):
        try:
            stock_info = ak.stock_info_a_code_name()
            for _, row in stock_info.iterrows():
                code = row['code']
                name = row['name']
                if code.startswith(('sh', 'sz')):
                    code = code[2:]
                self.name_map[code] = name
            self.log(f"已加载 {len(self.name_map)} 只股票名称")
        except Exception as e:
            self.log(f"AKShare 获取股票名称失败: {e}，使用手动映射")
            self.name_map = {'600519': '贵州茅台', '000001': '平安银行'}

    def _init_technical_indicators(self):
        for symbol in self.symbols:
            try:
                df = self.reader.daily(symbol=symbol)
                if df is None or df.empty:
                    self.log(f"警告：{symbol} 无历史数据")
                    continue
                df = df.sort_index()
                df['ma_short'] = df['close'].rolling(self.ma_short).mean()
                df['ma_long'] = df['close'].rolling(self.ma_long).mean()
                last = df.iloc[-1]
                self.signals[symbol] = {
                    'ma_short': last['ma_short'],
                    'ma_long': last['ma_long'],
                    'last_close': last['close']
                }
                self.historical_data[symbol] = {
                    'price': last['close'],
                    'ma_short': last['ma_short'],
                    'ma_long': last['ma_long'],
                    'last_close': last['close'],
                    'date': df.index[-1].strftime('%Y-%m-%d'),
                    'df': df.tail(250)
                }
            except Exception as e:
                self.log(f"计算{symbol}指标失败: {e}")

    def _refresh_sector_cache(self):
        try:
            df_block = self.reader.block(symbol='block_gn.dat', group=True)
            if df_block is not None and not df_block.empty:
                for _, row in df_block.iterrows():
                    code = row.get('code')
                    industry = row.get('blockname')
                    if code and industry and code in self.symbols:
                        self.sector_cache[code] = industry
                for symbol in self.symbols:
                    if symbol not in self.sector_cache:
                        self.sector_cache[symbol] = "未分类"
                self.log(f"细分行业已更新 (本地)")
                return
        except Exception as e:
            self.log(f"本地行业文件读取失败: {e}，尝试在线获取...")
        try:
            industry_df = ak.stock_board_industry_summary_ths()
            if industry_df is not None and not industry_df.empty:
                for symbol in self.symbols:
                    self.sector_cache[symbol] = "获取中..."
                self.log(f"细分行业已更新 (在线)")
                return
        except Exception as e:
            self.log(f"在线行业数据获取失败: {e}")
        for symbol in self.symbols:
            if symbol not in self.sector_cache:
                self.sector_cache[symbol] = "未分类"

    def _show_historical_data(self):
        self.table.setRowCount(len(self.symbols))
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        for i, symbol in enumerate(self.symbols):
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
            signal = "历史参考"
            col = TableCol.CODE
            self.table.setItem(i, col, QTableWidgetItem(symbol))
            col = TableCol.NAME
            self.table.setItem(i, col, QTableWidgetItem(name))
            col = TableCol.INDUSTRY
            self.table.setItem(i, col, QTableWidgetItem(industry))
            col = TableCol.PRICE
            self.table.setItem(i, col, QTableWidgetItem(f"{price:.2f}" if price else "无数据"))
            col = TableCol.CHANGE
            self.table.setItem(i, col, QTableWidgetItem(f"{change:+.2f}" if price else "无数据"))
            col = TableCol.SPEED
            self.table.setItem(i, col, QTableWidgetItem("-"))
            col = TableCol.MA_SHORT
            self.table.setItem(i, col, QTableWidgetItem(f"{ma_short:.2f}" if ma_short else "无数据"))
            col = TableCol.MA_LONG
            self.table.setItem(i, col, QTableWidgetItem(f"{ma_long:.2f}" if ma_long else "无数据"))
            if self.show_macd:
                col = TableCol.MACD
                self.table.setItem(i, col, QTableWidgetItem("N/A"))
            if self.show_rsi:
                col = TableCol.RSI
                self.table.setItem(i, col, QTableWidgetItem("N/A"))
            if self.show_kdj:
                col = TableCol.KDJ_K
                self.table.setItem(i, col, QTableWidgetItem("N/A"))
            if self.show_boll:
                col = TableCol.BOLL_WIDTH
                self.table.setItem(i, col, QTableWidgetItem("N/A"))
            col = TableCol.SIGNAL
            self.table.setItem(i, col, QTableWidgetItem(signal))
            col = TableCol.STATUS
            self.table.setItem(i, col, QTableWidgetItem(f"历史({date_str})"))
            col = TableCol.UPDATE_TIME
            self.table.setItem(i, col, QTableWidgetItem(now_str))
            for c in range(self.table.columnCount()):
                item = self.table.item(i, c)
                if item:
                    item.setBackground(QColor(240, 240, 240))
        self.status_label.setText(f"显示历史数据（{now_str}）")

    def _start_data_thread(self):
        if self.data_thread:
            self.data_thread.stop()
            self.data_thread.wait()
        self.data_thread = DataFetcher(self.symbols, self.host, self.port)
        self.data_thread.data_ready.connect(self.on_data_received)
        self.data_thread.error_occurred.connect(self.on_data_error)
        self.data_thread.start()

    def on_data_received(self, quotes):
        now = datetime.datetime.now()
        now_str = now.strftime("%H:%M:%S")
        self.table.setRowCount(len(quotes))

        for i, (_, row) in enumerate(quotes.iterrows()):
            symbol = row['code']
            price = row['price']
            last_close = row['last_close']
            change = (price - last_close) / last_close * 100 if last_close else 0
            cur_vol = row.get('cur_vol', 0)

            name = self.name_map.get(symbol, "未知")
            industry = self.sector_cache.get(symbol, "加载中...")

            speed = 0
            last = self.last_data.get(symbol)
            if last:
                last_cur_vol = last.get('cur_vol', 0)
                last_time = last['time']
                time_diff = (now - last_time).total_seconds()
                if time_diff > 0 and last_cur_vol > 0:
                    vol_rate_per_sec = (cur_vol - last_cur_vol) / time_diff
                    speed = vol_rate_per_sec * 60
            self.last_data[symbol] = {'cur_vol': cur_vol, 'time': now}
            self.latest_quotes[symbol] = {
                'price': price,
                'change': change,
                'speed': speed,
                'cur_vol': cur_vol
            }

            sig = self.signals.get(symbol, {})
            ma_short = sig.get('ma_short', 0)
            ma_long = sig.get('ma_long', 0)

            macd_val = None
            rsi_val = None
            kdj_k = None
            boll_width = None
            df_hist = self.historical_data.get(symbol, {}).get('df')
            if df_hist is not None and not df_hist.empty:
                if self.show_macd and len(df_hist) >= 26:
                    macd_val = self.calc_macd(df_hist)
                if self.show_rsi and len(df_hist) >= 14:
                    rsi_val = self.calc_rsi(df_hist)
                if self.show_kdj and len(df_hist) >= 9:
                    kdj_k = self.calc_kdj_k(df_hist)
                if self.show_boll and len(df_hist) >= 20:
                    boll_width = self.calc_boll_width(df_hist)

            if price > ma_short:
                signal = "买入"
            elif price < ma_long:
                signal = "卖出"
            else:
                signal = "持有"

            for alert_symbol, condition in self.alerts:
                if alert_symbol == symbol:
                    try:
                        context = {'price': price, 'change': change, 'volume': cur_vol}
                        if safe_eval(condition, context):
                            self.notify(symbol, "预警触发", condition)
                    except Exception as e:
                        self.log(f"预警条件评估错误: {e}")

            col = TableCol.CODE
            self.table.setItem(i, col, QTableWidgetItem(symbol))
            col = TableCol.NAME
            self.table.setItem(i, col, QTableWidgetItem(name))
            col = TableCol.INDUSTRY
            self.table.setItem(i, col, QTableWidgetItem(industry))
            col = TableCol.PRICE
            self.table.setItem(i, col, QTableWidgetItem(f"{price:.2f}"))
            col = TableCol.CHANGE
            self.table.setItem(i, col, QTableWidgetItem(f"{change:+.2f}"))
            col = TableCol.SPEED
            self.table.setItem(i, col, QTableWidgetItem(f"{speed:.2f}"))
            col = TableCol.MA_SHORT
            self.table.setItem(i, col, QTableWidgetItem(f"{ma_short:.2f}"))
            col = TableCol.MA_LONG
            self.table.setItem(i, col, QTableWidgetItem(f"{ma_long:.2f}"))
            if self.show_macd:
                col = TableCol.MACD
                self.table.setItem(i, col, QTableWidgetItem(f"{macd_val:.2f}" if macd_val is not None else "N/A"))
            if self.show_rsi:
                col = TableCol.RSI
                self.table.setItem(i, col, QTableWidgetItem(f"{rsi_val:.2f}" if rsi_val is not None else "N/A"))
            if self.show_kdj:
                col = TableCol.KDJ_K
                self.table.setItem(i, col, QTableWidgetItem(f"{kdj_k:.2f}" if kdj_k is not None else "N/A"))
            if self.show_boll:
                col = TableCol.BOLL_WIDTH
                self.table.setItem(i, col, QTableWidgetItem(f"{boll_width:.4f}" if boll_width is not None else "N/A"))
            col = TableCol.SIGNAL
            self.table.setItem(i, col, QTableWidgetItem(signal))
            col = TableCol.STATUS
            self.table.setItem(i, col, QTableWidgetItem("实时"))
            col = TableCol.UPDATE_TIME
            self.table.setItem(i, col, QTableWidgetItem(now_str))

            if signal == "买入":
                self.table.item(i, TableCol.SIGNAL).setBackground(QColor(0, 255, 0, 100))
            elif signal == "卖出":
                self.table.item(i, TableCol.SIGNAL).setBackground(QColor(255, 0, 0, 100))

        self.status_label.setText(f"实时数据 {now_str}")
        self.status_info.setText(f"服务器: {self.host}:{self.port} | 最后更新: {now_str}")

        current_row = self.table.currentRow()
        if current_row >= 0:
            symbol = self.table.item(current_row, TableCol.CODE).text()
            if symbol != self.current_preview_symbol:
                self.current_preview_symbol = symbol
                self.update_preview(symbol)

    def on_data_error(self, err_msg):
        self.log(f"数据获取错误: {err_msg}")
        self.status_label.setText(f"数据错误: {err_msg}")

    def _update_status(self):
        if is_trading_time():
            self.status_label.setStyleSheet("")
        else:
            self.status_label.setStyleSheet("color: gray")
            self.status_label.setText("非交易时段，等待开盘...")

    def notify(self, symbol, title, msg):
        self.status_label.setStyleSheet("background-color: yellow")
        QTimer.singleShot(2000, lambda: self.status_label.setStyleSheet(""))
        if self.tray_icon and self.enable_notify:
            self.tray_icon.showMessage(f"{symbol} {title}", msg, QSystemTrayIcon.Information, 3000)

    def calc_macd(self, df):
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        dif = exp12 - exp26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = (dif - dea) * 2
        return macd.iloc[-1] if not macd.empty else None

    def calc_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else None

    def calc_kdj_k(self, df):
        low_list = df['low'].rolling(9).min()
        high_list = df['high'].rolling(9).max()
        rsv = (df['close'] - low_list) / (high_list - low_list) * 100
        k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
        return k.iloc[-1] if not k.empty else None

    def calc_boll_width(self, df):
        window = 20
        ma = df['close'].rolling(window).mean()
        std = df['close'].rolling(window).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        width = (upper - lower) / ma
        return width.iloc[-1] if not width.empty else None

    def update_preview(self, symbol):
        try:
            df = self.reader.daily(symbol=symbol)
            if df is None or df.empty:
                return
            df = df.tail(60).copy()
            df.index = pd.to_datetime(df.index)
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            self.preview_figure.clear()
            ax = self.preview_figure.add_subplot(111)
            mpf.plot(df, type='candle', style='charles', volume=False, mav=(5, 20), ax=ax,
                     datetime_format='%Y-%m-%d')
            ax.set_title(f'{symbol} 最近60天')
            ax.set_xlabel('')
            self.preview_canvas.draw()
        except Exception as e:
            self.log(f"预览更新失败 {symbol}: {e}")

    def on_current_cell_changed(self, current_row, current_col, previous_row, previous_col):
        if current_row >= 0:
            symbol = self.table.item(current_row, TableCol.CODE).text()
            if symbol != self.current_preview_symbol:
                self.current_preview_symbol = symbol
                self.update_preview(symbol)

    def manual_refresh(self):
        if is_trading_time():
            self._refresh_data()
        else:
            self.log("非交易时段，无需刷新")

    def _refresh_data(self):
        self._show_historical_data()

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存数据", "", "CSV Files (*.csv)")
        if path:
            data = []
            for row in range(self.table.rowCount()):
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item else "")
                data.append(row_data)
            import csv
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                writer.writerow(headers)
                writer.writerows(data)
            self.log(f"数据已导出至 {path}")

    def show_config_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("配置")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        host_edit = QLineEdit(self.host)
        port_edit = QLineEdit(str(self.port))
        interval_edit = QLineEdit(str(self.refresh_interval))
        sector_interval_edit = QLineEdit(str(self.sector_refresh_interval))
        commission_edit = QLineEdit(str(self.commission))
        slippage_edit = QLineEdit(str(self.slippage))
        form.addRow("行情服务器IP:", host_edit)
        form.addRow("端口:", port_edit)
        form.addRow("刷新间隔(ms):", interval_edit)
        form.addRow("行业刷新间隔(ms):", sector_interval_edit)
        form.addRow("佣金率:", commission_edit)
        form.addRow("滑点率:", slippage_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            self.host = host_edit.text()
            self.port = int(port_edit.text())
            self.refresh_interval = int(interval_edit.text())
            self.sector_refresh_interval = int(sector_interval_edit.text())
            self.commission = float(commission_edit.text())
            self.slippage = float(slippage_edit.text())
            self.save_settings()
            self._start_data_thread()
            self.log("配置已更新")

    def edit_symbols(self):
        dialog = StockSelectorDialog(self.symbols, self)
        if dialog.exec_() == QDialog.Accepted:
            new_symbols = dialog.get_selected_symbols()
            if new_symbols:
                self.symbols = new_symbols
                self.save_settings()
                self._start_data_thread()
                self.update_table_headers()
                self._init_technical_indicators()
                self._refresh_sector_cache()
                self._show_historical_data()
                self.log(f"监控股票已更新: {self.symbols}")

    def edit_indicators(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("技术指标设置")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        macd_cb = QCheckBox("显示MACD")
        macd_cb.setChecked(self.show_macd)
        rsi_cb = QCheckBox("显示RSI")
        rsi_cb.setChecked(self.show_rsi)
        kdj_cb = QCheckBox("显示KDJ_K")
        kdj_cb.setChecked(self.show_kdj)
        boll_cb = QCheckBox("显示布林带宽度")
        boll_cb.setChecked(self.show_boll)
        notify_cb = QCheckBox("启用通知")
        notify_cb.setChecked(self.enable_notify)
        form.addRow(macd_cb)
        form.addRow(rsi_cb)
        form.addRow(kdj_cb)
        form.addRow(boll_cb)
        form.addRow(notify_cb)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            self.show_macd = macd_cb.isChecked()
            self.show_rsi = rsi_cb.isChecked()
            self.show_kdj = kdj_cb.isChecked()
            self.show_boll = boll_cb.isChecked()
            self.enable_notify = notify_cb.isChecked()
            self.save_settings()
            self.update_table_headers()
            self._show_historical_data()
            self.log("指标设置已更新")

    def add_alert(self):
        symbol, ok = QInputDialog.getText(self, "添加预警", "股票代码:")
        if ok and symbol:
            condition, ok2 = QInputDialog.getText(self, "添加预警", "条件 (例如 price>1500, volume>100000, change>5):")
            if ok2 and condition:
                self.alerts.append((symbol.strip(), condition.strip()))
                self.save_settings()
                self.log(f"已添加预警: {symbol} {condition}")

    def clear_alerts(self):
        self.alerts = []
        self.save_settings()
        self.log("已清空所有预警")

    def show_favorites(self):
        if not self.favorites and not self.custom_groups.get('自选股', []):
            reply = QMessageBox.question(self, "自选股为空", "自选股列表为空，是否添加一些股票？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.edit_symbols()
            return
        dialog = FavoritesManagerDialog(self.favorites, self.name_map, self.sector_cache, self)
        dialog.exec_()

    def open_group_manager(self):
        dialog = GroupManagerDialog(self.custom_groups, self.name_map, self)
        if dialog.exec_() == QDialog.Accepted:
            self.update_table_headers()
            self.log("板块已更新")

    def import_from_tdx_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择通达信导出的CSV文件", "", "CSV Files (*.csv)")
        if path:
            try:
                df = pd.read_csv(path, encoding='gbk')
                code_col = None
                for col in df.columns:
                    if '代码' in col or 'code' in col.lower():
                        code_col = col
                        break
                if code_col is None:
                    QMessageBox.warning(self, "错误", "未找到代码列")
                    return
                codes = df[code_col].astype(str).str.replace(r'\D', '', regex=True).tolist()
                if '自选股' not in self.custom_groups:
                    self.custom_groups['自选股'] = []
                existing = set(self.custom_groups['自选股'])
                new_codes = [c for c in codes if c not in existing]
                self.custom_groups['自选股'].extend(new_codes)
                self.favorites = self.custom_groups['自选股'].copy()
                self.save_custom_groups()
                self.save_settings()
                self.log(f"从 {path} 导入 {len(new_codes)} 只股票到自选股")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入失败: {e}")

    def show_table_context_menu(self, pos):
        menu = QMenu()
        open_kline_action = QAction("打开详细K线图", self)
        open_kline_action.triggered.connect(self.open_detailed_kline)
        set_alert_action = QAction("设置预警", self)
        set_alert_action.triggered.connect(self.set_alert_for_current)
        add_favorite_action = QAction("加入自选股", self)
        add_favorite_action.triggered.connect(self.add_current_to_favorites)
        menu.addAction(open_kline_action)
        menu.addAction(set_alert_action)
        menu.addAction(add_favorite_action)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def open_detailed_kline(self):
        row = self.table.currentRow()
        if row >= 0:
            symbol = self.table.item(row, TableCol.CODE).text()
            dialog = KLineDialog(symbol, self.reader, self)
            dialog.exec_()

    def set_alert_for_current(self):
        row = self.table.currentRow()
        if row < 0:
            return
        symbol = self.table.item(row, TableCol.CODE).text()
        condition, ok = QInputDialog.getText(self, "设置预警", f"为 {symbol} 设置预警条件 (例如 price>1500):")
        if ok and condition:
            self.alerts.append((symbol, condition))
            self.save_settings()
            self.log(f"已添加预警: {symbol} {condition}")

    def add_current_to_favorites(self):
        row = self.table.currentRow()
        if row < 0:
            return
        symbol = self.table.item(row, TableCol.CODE).text()
        if symbol not in self.favorites:
            self.favorites.append(symbol)
            if '自选股' not in self.custom_groups:
                self.custom_groups['自选股'] = []
            if symbol not in self.custom_groups['自选股']:
                self.custom_groups['自选股'].append(symbol)
            self.save_settings()
            self.save_custom_groups()
            self.log(f"{symbol} 已加入自选股")
        else:
            self.log(f"{symbol} 已在自选股中")

    def on_item_double_clicked(self, item):
        row = item.row()
        symbol_item = self.table.item(row, TableCol.CODE)
        if symbol_item:
            symbol = symbol_item.text()
            dialog = KLineDialog(symbol, self.reader, self)
            dialog.exec_()

    def show_ai_factor_dialog(self):
        if not GPLEARN_AVAILABLE:
            QMessageBox.critical(self, "错误", "gplearn未安装，无法进行因子挖掘。请安装：pip install gplearn")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("自动因子挖掘")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("选择股票:"))
        stock_combo = QComboBox()
        stock_combo.addItems(self.symbols)
        layout.addWidget(stock_combo)

        layout.addWidget(QLabel("遗传编程代数:"))
        gen_spin = QSpinBox()
        gen_spin.setRange(1, 100)
        gen_spin.setValue(20)
        layout.addWidget(gen_spin)

        run_btn = QPushButton("开始挖掘")
        output = QTextEdit()
        output.setReadOnly(True)
        layout.addWidget(run_btn)
        layout.addWidget(output)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.accept)
        layout.addWidget(button_box)

        def on_run():
            symbol = stock_combo.currentText()
            output.clear()
            output.append(f"正在为 {symbol} 挖掘因子...")
            try:
                df = self.reader.daily(symbol=symbol)
                if df.empty:
                    output.append("无历史数据")
                    return
                df = df.sort_index()
                df['target'] = df['close'].shift(-5) / df['close'] - 1
                df = df.dropna()
                if len(df) < 100:
                    output.append("数据量不足")
                    return

                miner = AutoFactorMiner(generations=gen_spin.value())
                X = miner.create_features(df)
                y = df['target']
                miner.fit(X, y)
                X_new = miner.transform(X)
                new_factors = [c for c in X_new.columns if c.startswith('alpha_')]
                if new_factors:
                    output.append(f"挖掘到 {len(new_factors)} 个因子：")
                    for f in new_factors:
                        ic = miner.evaluate_factor(X_new, f, y)
                        output.append(f"  {f} (IC: {ic:.4f})")
                else:
                    output.append("未发现有效因子")
            except Exception as e:
                output.append(f"错误: {e}")
                logger.error(traceback.format_exc())

        run_btn.clicked.connect(on_run)
        dialog.exec_()

    def show_ai_strategy_dialog(self):
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("AI策略生成")
            dialog.resize(700, 600)

            layout = QVBoxLayout(dialog)

            scheme_layout = QHBoxLayout()
            scheme_layout.addWidget(QLabel("AI方案:"))
            scheme_combo = QComboBox()
            scheme_combo.addItems(["免费本地模型 (Ollama)", "DeepSeek API (付费)", "模拟生成(测试)"])
            scheme_layout.addWidget(scheme_combo)
            scheme_layout.addStretch()
            layout.addLayout(scheme_layout)

            model_widget = QWidget()
            model_layout = QHBoxLayout(model_widget)
            model_layout.addWidget(QLabel("本地模型:"))
            model_combo = QComboBox()
            model_combo.addItems(["qwen2.5-coder:7b", "llama3.2:3b"])
            model_layout.addWidget(model_combo)
            model_layout.addStretch()
            layout.addWidget(model_widget)

            api_key_widget = QWidget()
            api_key_layout = QHBoxLayout(api_key_widget)
            api_key_layout.addWidget(QLabel("DeepSeek API Key:"))
            api_key_edit = QLineEdit()
            api_key_edit.setEchoMode(QLineEdit.Password)
            api_key_layout.addWidget(api_key_edit)
            api_key_layout.addStretch()
            api_key_widget.setVisible(False)
            layout.addWidget(api_key_widget)

            layout.addWidget(QLabel("策略描述:"))
            desc_edit = QTextEdit()
            desc_edit.setPlaceholderText("例如：当5日均线上穿20日均线且成交量放大1.2倍时买入，止损5%")
            desc_edit.setFixedHeight(100)
            layout.addWidget(desc_edit)

            gen_btn = QPushButton("生成策略代码")
            layout.addWidget(gen_btn)

            layout.addWidget(QLabel("生成的代码:"))
            code_edit = QTextEdit()
            code_edit.setFontFamily("Courier New")
            layout.addWidget(code_edit)

            save_btn = QPushButton("保存策略文件")
            layout.addWidget(save_btn)

            def on_scheme_changed(idx):
                scheme = scheme_combo.currentText()
                if "免费" in scheme:
                    model_widget.setVisible(True)
                    api_key_widget.setVisible(False)
                elif "DeepSeek" in scheme:
                    model_widget.setVisible(False)
                    api_key_widget.setVisible(True)
                else:
                    model_widget.setVisible(False)
                    api_key_widget.setVisible(False)

            scheme_combo.currentIndexChanged.connect(on_scheme_changed)

            def on_generate():
                desc = desc_edit.toPlainText().strip()
                if not desc:
                    QMessageBox.warning(dialog, "警告", "请输入策略描述")
                    return
                gen_btn.setEnabled(False)
                try:
                    scheme = scheme_combo.currentText()
                    if "免费" in scheme:
                        if not OLLAMA_AVAILABLE:
                            QMessageBox.critical(dialog, "错误", "ollama未安装，请安装：pip install ollama")
                            return
                        try:
                            import socket
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(1)
                            result = sock.connect_ex(('127.0.0.1', 11434))
                            sock.close()
                            if result != 0:
                                QMessageBox.critical(dialog, "错误", "Ollama 服务未运行，请先启动 ollama serve")
                                return
                        except:
                            pass
                        model = model_combo.currentText()
                        prompt = f"""你是一个量化策略专家。请根据以下描述生成Python策略代码，继承自BaseStrategy，包含__init__和next方法。只返回代码，不要解释。

描述：{desc}
"""
                        response = ollama.generate(model=model, prompt=prompt, options={"temperature": 0.2})
                        code = response.get('response', '')
                        if '```python' in code:
                            code = code.split('```python')[1].split('```')[0].strip()
                        code_edit.setPlainText(code)
                    elif "DeepSeek" in scheme:
                        api_key = api_key_edit.text().strip()
                        if not api_key:
                            QMessageBox.warning(dialog, "警告", "请填写DeepSeek API Key")
                            return
                        if not OPENAI_AVAILABLE:
                            QMessageBox.critical(dialog, "错误", "openai未安装，请安装：pip install openai")
                            return
                        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                        prompt = f"生成量化策略代码：{desc}"
                        response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.2
                        )
                        code = response.choices[0].message.content
                        if '```python' in code:
                            code = code.split('```python')[1].split('```')[0].strip()
                        code_edit.setPlainText(code)
                    else:
                        code = f"""# 模拟生成的策略代码
# 描述：{desc}
class Strategy:
    def __init__(self, params):
        self.ma_short = params.get('ma_short', 5)
        self.ma_long = params.get('ma_long', 20)

    def next(self, data):
        if data['close'][-1] > data['ma_short'][-1]:
            return 'buy'
        return 'hold'
"""
                        code_edit.setPlainText(code)
                except Exception as e:
                    QMessageBox.critical(dialog, "错误", f"生成失败: {e}")
                finally:
                    gen_btn.setEnabled(True)

            gen_btn.clicked.connect(on_generate)

            def on_save():
                code = code_edit.toPlainText()
                if not code:
                    QMessageBox.warning(dialog, "警告", "没有可保存的代码")
                    return
                filename, _ = QFileDialog.getSaveFileName(dialog, "保存策略", "", "Python文件 (*.py)")
                if filename:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(code)
                    QMessageBox.information(dialog, "成功", f"策略已保存至 {filename}")

            save_btn.clicked.connect(on_save)

            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开AI策略生成对话框失败: {e}")

    def show_backtest_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("回测与优化")
        dialog.resize(600, 500)

        layout = QVBoxLayout(dialog)

        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("策略文件:"))
        file_edit = QLineEdit()
        file_btn = QPushButton("浏览")
        file_layout.addWidget(file_edit)
        file_layout.addWidget(file_btn)
        layout.addLayout(file_layout)

        stock_layout = QHBoxLayout()
        stock_layout.addWidget(QLabel("股票代码:"))
        stock_combo = QComboBox()
        stock_combo.addItems(self.symbols)
        stock_layout.addWidget(stock_combo)
        stock_layout.addStretch()
        layout.addLayout(stock_layout)

        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("初始资金:"))
        capital_edit = QLineEdit("1000000")
        param_layout.addWidget(capital_edit)
        param_layout.addWidget(QLabel("手续费率:"))
        commission_edit = QLineEdit(str(self.commission))
        param_layout.addWidget(commission_edit)
        layout.addLayout(param_layout)

        optimize_btn = QPushButton("启用贝叶斯优化")
        optimize_btn.setCheckable(True)
        layout.addWidget(optimize_btn)

        param_space_layout = QVBoxLayout()
        param_space_layout.addWidget(QLabel("参数空间 (仅优化时使用):"))
        ma_short_min = QSpinBox()
        ma_short_min.setRange(1, 50)
        ma_short_min.setValue(5)
        ma_short_max = QSpinBox()
        ma_short_max.setRange(1, 50)
        ma_short_max.setValue(20)
        ma_long_min = QSpinBox()
        ma_long_min.setRange(1, 100)
        ma_long_min.setValue(20)
        ma_long_max = QSpinBox()
        ma_long_max.setRange(1, 100)
        ma_long_max.setValue(50)
        param_space_layout.addWidget(QLabel("ma_short 范围:"))
        param_space_layout.addWidget(ma_short_min)
        param_space_layout.addWidget(QLabel("~"))
        param_space_layout.addWidget(ma_short_max)
        param_space_layout.addWidget(QLabel("ma_long 范围:"))
        param_space_layout.addWidget(ma_long_min)
        param_space_layout.addWidget(QLabel("~"))
        param_space_layout.addWidget(ma_long_max)
        layout.addLayout(param_space_layout)

        run_btn = QPushButton("运行回测")
        layout.addWidget(run_btn)

        progress = QProgressBar()
        progress.setVisible(False)
        layout.addWidget(progress)

        result_text = QTextEdit()
        result_text.setReadOnly(True)
        layout.addWidget(result_text)

        def on_file_browse():
            filename, _ = QFileDialog.getOpenFileName(dialog, "选择策略文件", "", "Python文件 (*.py)")
            if filename:
                file_edit.setText(filename)

        file_btn.clicked.connect(on_file_browse)

        worker = None

        def on_run():
            nonlocal worker
            strategy_file = file_edit.text().strip()
            if not strategy_file:
                QMessageBox.warning(dialog, "警告", "请选择策略文件")
                return
            symbol = stock_combo.currentText()
            capital = float(capital_edit.text())
            commission = float(commission_edit.text())
            optimize = optimize_btn.isChecked()
            param_space = {}
            if optimize:
                param_space = {
                    'ma_short': (ma_short_min.value(), ma_short_max.value()),
                    'ma_long': (ma_long_min.value(), ma_long_max.value())
                }

            worker = BacktestWorker(strategy_file, symbol, capital, commission, self.slippage, self.tdx_dir, optimize,
                                    param_space)
            worker.progress.connect(progress.setValue)
            worker.result_ready.connect(on_result_ready)
            worker.error_occurred.connect(on_error)
            worker.finished.connect(lambda: progress.setVisible(False))

            run_btn.setEnabled(False)
            progress.setVisible(True)
            progress.setValue(0)
            result_text.clear()
            result_text.append("回测进行中...")
            worker.start()

        def on_result_ready(result):
            run_btn.setEnabled(True)
            result_text.append("回测完成:")
            result_text.append(f"总收益率: {result['total_return']:.2f}%")
            result_text.append(f"夏普比率: {result['sharpe']:.4f}")
            result_text.append(f"最大回撤: {result['max_drawdown']:.2f}%")
            result_text.append(f"最终资金: {result['final_capital']:.2f}")
            result_text.append(f"交易次数: {len(result['trades'])}")
            if 'best_params' in result:
                result_text.append(f"最优参数: {result['best_params']}")
                result_text.append(f"最优夏普: {result['best_sharpe']:.4f}")

        def on_error(err_msg):
            run_btn.setEnabled(True)
            progress.setVisible(False)
            QMessageBox.critical(dialog, "错误", f"回测失败: {err_msg}")

        run_btn.clicked.connect(on_run)
        dialog.exec_()

    def show_risk_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("智能风控设置")
        layout = QVBoxLayout(dialog)

        group1 = QGroupBox("动态止损")
        form1 = QFormLayout(group1)
        stop_mult = QDoubleSpinBox()
        stop_mult.setRange(1.0, 5.0)
        stop_mult.setSingleStep(0.5)
        stop_mult.setValue(self.risk_manager.stop_loss_mult)
        form1.addRow("ATR倍数:", stop_mult)
        layout.addWidget(group1)

        group2 = QGroupBox("仓位管理")
        form2 = QFormLayout(group2)
        risk_per_trade = QDoubleSpinBox()
        risk_per_trade.setRange(0.01, 0.10)
        risk_per_trade.setSingleStep(0.01)
        risk_per_trade.setValue(self.risk_manager.risk_per_trade)
        form2.addRow("单笔风险比例:", risk_per_trade)
        layout.addWidget(group2)

        group3 = QGroupBox("产业风险预警")
        gnn_cb = QCheckBox("启用GNN产业风险监测")
        gnn_cb.setChecked(self.risk_manager.use_gnn)
        group3.setLayout(QVBoxLayout())
        group3.layout().addWidget(gnn_cb)
        layout.addWidget(group3)

        save_btn = QPushButton("保存设置")
        layout.addWidget(save_btn)

        def on_save():
            self.risk_manager.stop_loss_mult = stop_mult.value()
            self.risk_manager.risk_per_trade = risk_per_trade.value()
            self.risk_manager.use_gnn = gnn_cb.isChecked()
            self.save_settings()
            self.log("风控设置已保存")
            dialog.accept()

        save_btn.clicked.connect(on_save)
        dialog.exec_()

    def show_autopilot_dialog(self):
        dialog = AutoPilotDialog(self)
        dialog.exec_()

    def get_latest_data(self) -> Dict[str, pd.DataFrame]:
        data = {}
        for symbol in self.symbols:
            hist = self.historical_data.get(symbol, {}).get('df')
            if hist is not None and not hist.empty:
                required = ['open', 'high', 'low', 'close', 'volume']
                if all(col in hist.columns for col in required):
                    data[symbol] = hist[required].copy()
        return data

    def get_current_positions(self) -> Dict[str, float]:
        positions = {}
        if self.symbols:
            total_value = 1e6
            weight = 1.0 / len(self.symbols)
            for sym in self.symbols:
                price = self.latest_quotes.get(sym, {}).get('price', 0)
                if price > 0:
                    positions[sym] = total_value * weight
        return positions

    def closeEvent(self, event):
        if self.data_thread:
            self.data_thread.stop()
            self.data_thread.wait()
        if self.tray_icon:
            self.tray_icon.hide()
        self.save_settings()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = QuantMonitor()
    window.show()
    sys.exit(app.exec_())