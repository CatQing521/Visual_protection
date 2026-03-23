# core/kalman_filter.py
# 自适应卡尔曼滤波器 + 基于 Welford 在线算法的马氏距离异常检测器
# 核心运算全部手写，仅依赖 numpy 基础矩阵操作（不调用 linalg.inv / scipy 等）

import numpy as np
import config


# ══════════════════════════════════════════════════════════════════
# 辅助函数：手写高斯-约当消元法求方阵逆矩阵
# ══════════════════════════════════════════════════════════════════

def _gauss_jordan_inverse(mat: np.ndarray) -> np.ndarray:
    """
    手写高斯-约当消元法求逆矩阵，不调用 np.linalg.inv。

    算法步骤：
      1. 构造增广矩阵 [A | I]
      2. 对左半部分做初等行变换化为单位矩阵
      3. 右半部分即为 A 的逆矩阵

    若矩阵奇异（主元 < 1e-12），返回单位矩阵作为降级处理，保证系统不崩溃。
    """
    n = mat.shape[0]
    # 构造增广矩阵 [A | I]，转为 float 避免整数溢出
    aug = np.zeros((n, 2 * n), dtype=float)
    aug[:, :n] = mat.astype(float)
    aug[:, n:] = np.eye(n)

    for col in range(n):
        # ── 列主元选取（减少数值误差）────────────────
        pivot_row = col
        max_val   = abs(aug[col, col])
        for row in range(col + 1, n):
            if abs(aug[row, col]) > max_val:
                max_val   = abs(aug[row, col])
                pivot_row = row

        if max_val < 1e-12:
            return np.eye(n)   # 奇异矩阵降级

        # ── 交换行 ───────────────────────────────────
        aug[[col, pivot_row]] = aug[[pivot_row, col]]

        # ── 归一化主元行 ─────────────────────────────
        aug[col] = aug[col] / aug[col, col]

        # ── 消去该列所有其他行 ───────────────────────
        for row in range(n):
            if row != col:
                factor    = aug[row, col]
                aug[row] -= factor * aug[col]

    return aug[:, n:]


# ══════════════════════════════════════════════════════════════════
# 一维自适应卡尔曼滤波器
# ══════════════════════════════════════════════════════════════════

class AdaptiveKalmanFilter1D:
    """
    一维自适应卡尔曼滤波器，用于平滑 θ1-θ4 及视距的帧间抖动。

    状态向量：x = [角度, 角速度]ᵀ  （2维）

    标准卡尔曼方程：
      预测：x̂⁻  = F · x̂
            P⁻   = F · P · Fᵀ + Q
      更新：e    = z - H · x̂⁻          （新息）
            S    = H · P⁻ · Hᵀ + R     （新息协方差）
            K    = P⁻ · Hᵀ / S         （卡尔曼增益）
            x̂    = x̂⁻ + K · e
            P    = (I - K·H) · P⁻

    ── 本文改进：新息自适应 R ──────────────────────────────────
    标准 KF 的 R（观测噪声）固定不变，无法适应孩子坐姿的动静变化。
    本改进利用滑动窗口内的新息序列动态估计 R：

        R_k = (1-α)·R_{k-1} + α·max(e²_k - H·P⁻·Hᵀ, ε)

    • 孩子静止时：新息小 → R 收缩 → 更信任测量，角度收敛快
    • 孩子快速移动时：新息大 → R 扩张 → 更信任模型，避免过度跟随噪声
    """

    def __init__(self,
                 dt: float = 1.0 / 30,
                 process_noise: float = None,
                 obs_noise: float = None,
                 alpha: float = 0.1):
        """
        dt           : 采样时间间隔（秒），默认 1/30s（30fps）
        process_noise: 过程噪声 q，控制模型不确定性
        obs_noise    : 观测噪声 R 初始值
        alpha        : 自适应学习率（0~1），越大跟随越快
        """
        self.dt    = dt
        self.alpha = alpha

        # ── 状态转移矩阵 F ───────────────────────────
        # x_{k} = F · x_{k-1}  →  角度 += 角速度 × dt
        self.F = np.array([[1.0, dt ],
                           [0.0, 1.0]])

        # ── 观测矩阵 H ───────────────────────────────
        # 只观测角度（第一个分量）
        self.H = np.array([[1.0, 0.0]])

        # ── 过程噪声协方差 Q ─────────────────────────
        q = process_noise if process_noise is not None else config.KALMAN_PROCESS_NOISE
        self.Q = np.array([[q,       0.0  ],
                           [0.0,     q * 10]])  # 角速度不确定性略大

        # ── 观测噪声 R（标量，自适应更新）────────────
        self.R = obs_noise if obs_noise is not None else config.KALMAN_OBS_NOISE

        # ── 状态与协方差初始化 ───────────────────────
        self.x = np.array([[0.0], [0.0]])  # [角度; 角速度]
        self.P = np.eye(2) * 1.0

        self._initialized = False

    # ── 公共接口 ─────────────────────────────────────
    def update(self, measurement: float) -> float:
        """
        输入原始角度测量值（°），返回滤波后的平滑角度估计。
        首帧直接用测量值初始化，无需预热。
        """
        if not self._initialized:
            self.x[0, 0] = measurement
            self._initialized = True
            return measurement

        # ── 预测步 ───────────────────────────────────
        x_pred = self.F @ self.x                          # 2×1
        P_pred = self.F @ self.P @ self.F.T + self.Q     # 2×2

        # ── 计算新息 e = z - H·x̂⁻ ───────────────────
        z = np.array([[measurement]])
        H_x_pred  = float((self.H @ x_pred)[0, 0])
        innovation = measurement - H_x_pred              # 标量

        # ── 新息方差：S = H·P⁻·Hᵀ ──────────────────
        H_P_Ht = float((self.H @ P_pred @ self.H.T)[0, 0])

        # ── 自适应更新 R ─────────────────────────────
        # 用新息平方估计真实 R，减去系统本身贡献的 H·P⁻·Hᵀ
        raw_R_estimate = innovation ** 2 - H_P_Ht
        self.R = (1.0 - self.alpha) * self.R + self.alpha * max(raw_R_estimate, 1e-6)

        # ── 更新步 ───────────────────────────────────
        S = H_P_Ht + self.R                               # 标量
        K = (P_pred @ self.H.T) / S                      # 2×1 卡尔曼增益

        self.x = x_pred + K * innovation                 # 2×1
        I_KH   = np.eye(2) - K @ self.H                  # 2×2
        self.P = I_KH @ P_pred                            # 更新协方差

        return float(self.x[0, 0])

    def reset(self):
        """重置滤波器状态（新会话开始时调用）"""
        self.x            = np.array([[0.0], [0.0]])
        self.P            = np.eye(2) * 1.0
        self._initialized = False


# ══════════════════════════════════════════════════════════════════
# 在线马氏距离异常检测器
# ══════════════════════════════════════════════════════════════════

class OnlineMahalanobisDetector:
    """
    基于 Welford 在线算法的马氏距离异常检测器。

    ── 解决的问题 ──────────────────────────────────────────────────
    原系统对 θ1-θ4 各自独立设阈值，忽略了维度间的相关性：
    例如 θ1=7.9°（< 8°）且 θ3=14.8°（< 15°）单独不报警，
    但两者同时偏离说明复合不良姿态，应当检测。

    马氏距离将五维姿态向量 [θ1, θ2, θ3, θ4, dist] 整体衡量
    偏离正常分布的程度：

        D_M(x) = √( (x-μ)ᵀ · Σ⁻¹ · (x-μ) )

    D_M > threshold 时判定为综合姿态异常。

    ── 本文改进：Welford 在线协方差 ────────────────────────────────
    标准马氏距离需要提前准备完整数据集。本改进用 Welford 算法
    增量更新均值和协方差，边运行边学习每个孩子的正常姿态基线：

        δ   = x_k - μ_{k-1}
        μ_k = μ_{k-1} + δ / k
        δ₂  = x_k - μ_k
        M_k = M_{k-1} + δ ⊗ δ₂       （外积累加）
        Σ   = M_k / (k - 1)           （无偏协方差估计）

    协方差矩阵求逆使用手写高斯-约当消元法，不调用库函数。
    """

    def __init__(self,
                 dim: int        = 5,
                 threshold: float = None,
                 warmup: int     = 60,
                 inv_freq: int   = 30):
        """
        dim       : 观测向量维度（默认5：θ1~θ4 + 视距）
        threshold : 马氏距离异常阈值
        warmup    : 热身帧数，积累足够数据前不检测
        inv_freq  : 每隔多少帧重算一次协方差逆矩阵
        """
        self.dim       = dim
        self.threshold = threshold if threshold is not None else config.MAHAL_THRESHOLD
        self.warmup    = warmup
        self.inv_freq  = inv_freq

        # ── Welford 算法状态 ─────────────────────────
        self.n    = 0
        self.mean = np.zeros(dim)        # 在线均值
        self.M2   = np.zeros((dim, dim)) # 协方差累加矩阵

        # ── 逆矩阵缓存 ───────────────────────────────
        self._inv_cov      = None
        self._update_count = 0

    # ── 公共接口 ─────────────────────────────────────
    def update(self, x: np.ndarray, is_normal: bool = True):
        """
        输入当前帧的5维姿态向量，更新在线均值与协方差。

        is_normal: 只在无阈值告警时更新基线，防止异常帧污染正常分布。
        """
        if not is_normal:
            return

        self.n += 1

        # ── Welford 增量更新 ─────────────────────────
        delta      = x - self.mean
        self.mean += delta / self.n          # 更新均值
        delta2     = x - self.mean
        self.M2   += np.outer(delta, delta2) # 外积累加

        # ── 定期刷新逆矩阵缓存 ───────────────────────
        self._update_count += 1
        if self._update_count >= self.inv_freq:
            self._refresh_inv_cov()
            self._update_count = 0

    def distance(self, x: np.ndarray) -> float:
        """
        计算向量 x 到正常姿态分布中心的马氏距离。
        热身期未满或协方差未初始化时返回 0.0。
        """
        if self.n < self.warmup or self._inv_cov is None:
            return 0.0

        diff = x - self.mean
        # D² = diffᵀ · Σ⁻¹ · diff
        d_sq = float(diff @ self._inv_cov @ diff)
        return float(np.sqrt(max(d_sq, 0.0)))

    def is_anomaly(self, x: np.ndarray) -> bool:
        """马氏距离超过阈值则判定为综合姿态异常"""
        return self.distance(x) > self.threshold

    def ready(self) -> bool:
        """是否已积累足够帧数可进行异常检测"""
        return self.n >= self.warmup and self._inv_cov is not None

    def reset(self):
        """重置（新会话开始时调用）"""
        self.n             = 0
        self.mean          = np.zeros(self.dim)
        self.M2            = np.zeros((self.dim, self.dim))
        self._inv_cov      = None
        self._update_count = 0

    # ── 内部方法 ─────────────────────────────────────
    def _refresh_inv_cov(self):
        """重新计算并缓存协方差逆矩阵"""
        if self.n < 2:
            return
        cov = self.M2 / (self.n - 1)
        # 正则化：防止协方差矩阵奇异（各维度方差过小时）
        cov += np.eye(self.dim) * 1e-4
        self._inv_cov = _gauss_jordan_inverse(cov)