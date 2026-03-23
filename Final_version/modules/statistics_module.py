# modules/statistics_module.py — 用眼习惯统计与可视化

import io
from datetime import date, timedelta
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import QWidget, QVBoxLayout

DARK_BG   = "#0D1117"
CARD_BG   = "#161B22"
GRID_CLR  = "#21262D"
TEXT_CLR  = "#E6EDF3"
SUB_CLR   = "#8B949E"
BLUE      = "#58A6FF"
GREEN     = "#3FB950"
ORANGE    = "#F0883E"
RED       = "#F85149"
PURPLE    = "#BC8CFF"

import matplotlib.font_manager as fm
import platform

def _get_chinese_font():
    """自动检测系统可用中文字体"""
    system = platform.system()
    candidates = {
        "Windows": ["Microsoft YaHei", "SimHei", "SimSun", "FangSong"],
        "Darwin" : ["SimHei", "Heiti SC", "STHeiti", "Arial Unicode MS"],
        "Linux"  : ["WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Noto Sans CJK SC",
                    "Noto Sans SC", "DejaVu Sans"],
    }
    available = {f.name for f in fm.fontManager.ttflist}
    for font in candidates.get(system, []) + ["DejaVu Sans"]:
        if font in available:
            return font
    return "sans-serif"

_CJK_FONT = _get_chinese_font()

plt.rcParams.update({
    "figure.facecolor"   : DARK_BG,
    "axes.facecolor"     : CARD_BG,
    "axes.edgecolor"     : GRID_CLR,
    "axes.labelcolor"    : TEXT_CLR,
    "xtick.color"        : SUB_CLR,
    "ytick.color"        : SUB_CLR,
    "text.color"         : TEXT_CLR,
    "grid.color"         : GRID_CLR,
    "grid.linestyle"     : "--",
    "grid.alpha"         : 0.5,
    "font.family"        : ["Microsoft YaHei", "PingFang SC", "sans-serif"],
    "font.size"          : 9,
    "axes.titlesize"     : 11,
    "axes.titlepad"      : 10,
    "legend.facecolor"   : CARD_BG,
    "legend.edgecolor"   : GRID_CLR,
    "legend.labelcolor"  : TEXT_CLR,
})


# ── 通用 Canvas 容器 ─────────────────────────────────────
class ChartWidget(QWidget):
    def __init__(self, fig: Figure, parent=None):
        super().__init__(parent)
        self.canvas = FigureCanvas(fig)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def update_figure(self, fig: Figure):
        self.canvas.figure = fig
        self.canvas.draw()


# ── 日报图表 ─────────────────────────────────────────────
def build_daily_figure(daily_stats: dict) -> Figure:
    fig = Figure(figsize=(10, 4), tight_layout=True)

    # 左：小时用眼时长
    ax1 = fig.add_subplot(1, 2, 1)
    hours     = list(daily_stats.get("hourly", {}).keys())
    durations = list(daily_stats.get("hourly", {}).values())
    bars = ax1.bar(hours, durations, color=BLUE, alpha=0.85, width=0.6)
    ax1.set_title("今日各时段用眼时长（分钟）")
    ax1.set_xlabel("小时")
    ax1.set_ylabel("分钟")
    ax1.grid(axis="y")
    ax1.set_xticks(range(0, 24, 2))
    ax1.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=7)
    # 标注最大值
    if durations:
        max_val = max(durations)
        if max_val > 0:
            max_idx = durations.index(max_val)
            ax1.annotate(f"{max_val}m",
                         xy=(hours[max_idx], max_val),
                         xytext=(0, 5), textcoords="offset points",
                         ha="center", color=ORANGE, fontsize=8)

    # 右：坐姿质量饼图
    ax2 = fig.add_subplot(1, 2, 2)
    good  = daily_stats.get("good_ratio", 50)
    bad   = 100 - good
    if good + bad > 0:
        wedges, texts, autotexts = ax2.pie(
            [good, bad], labels=["良好坐姿", "需改善"],
            autopct="%1.1f%%",
            colors=[GREEN, RED], startangle=140,
            wedgeprops={"edgecolor": DARK_BG, "linewidth": 2},
            textprops={"color": TEXT_CLR},
        )
        for at in autotexts:
            at.set_fontsize(9)
    ax2.set_title("今日坐姿质量分布")

    return fig


# ── 周报图表 ─────────────────────────────────────────────
def build_weekly_figure(weekly_stats: list) -> Figure:
    fig = Figure(figsize=(10, 5), tight_layout=True)

    dates     = [s["date"][-5:] for s in weekly_stats]    # MM-DD
    durations = [s["total_sec"] / 60 for s in weekly_stats]
    good_pct  = [s["good_ratio"] for s in weekly_stats]
    distances = [s["avg_distance"] for s in weekly_stats]

    # 上：用眼时长折线
    ax1 = fig.add_subplot(2, 2, (1, 2))
    ax1.fill_between(dates, durations, alpha=0.25, color=BLUE)
    ax1.plot(dates, durations, color=BLUE, marker="o", linewidth=2, markersize=5)
    ax1.set_title("近7日每日用眼时长（分钟）")
    ax1.set_ylabel("分钟")
    ax1.grid(axis="y")
    for i, v in enumerate(durations):
        if v > 0:
            ax1.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=8, color=BLUE)

    # 下左：良好坐姿率
    ax2 = fig.add_subplot(2, 2, 3)
    colors = [GREEN if g >= 70 else ORANGE if g >= 40 else RED for g in good_pct]
    ax2.bar(dates, good_pct, color=colors, alpha=0.85, width=0.6)
    ax2.axhline(70, color=GREEN, linewidth=1, linestyle="--", alpha=0.7, label="良好线70%")
    ax2.set_title("近7日良好坐姿率（%）")
    ax2.set_ylabel("%")
    ax2.set_ylim(0, 110)
    ax2.grid(axis="y")
    ax2.legend(fontsize=8)

    # 下右：平均视距
    ax3 = fig.add_subplot(2, 2, 4)
    ax3.plot(dates, distances, color=PURPLE, marker="s", linewidth=2, markersize=5)
    ax3.fill_between(dates, distances, alpha=0.2, color=PURPLE)
    ax3.axhline(50, color=GREEN, linewidth=1, linestyle="--", alpha=0.7, label="安全线50cm")
    ax3.set_title("近7日平均视距（cm）")
    ax3.set_ylabel("cm")
    ax3.set_ylim(0, max(max(distances, default=60) + 10, 70))
    ax3.grid(axis="y")
    ax3.legend(fontsize=8)

    return fig


# ── 长期趋势图表 ─────────────────────────────────────────
def build_longterm_figure(longterm_stats: list) -> Figure:
    fig = Figure(figsize=(10, 6), tight_layout=True)

    n      = len(longterm_stats)
    x      = list(range(n))
    labels = [s["date"][-5:] for s in longterm_stats]
    durations = np.array([s["total_sec"] / 60 for s in longterm_stats])
    good_pct  = np.array([s["good_ratio"] for s in longterm_stats])
    distances = np.array([s["avg_distance"] for s in longterm_stats])

    def rolling_avg(arr, w=7):
        result = np.full_like(arr, np.nan)
        for i in range(len(arr)):
            lo = max(0, i - w + 1)
            result[i] = np.mean(arr[lo:i+1])
        return result

    tick_step = max(1, n // 10)

    # 用眼时长趋势
    ax1 = fig.add_subplot(3, 1, 1)
    ax1.bar(x, durations, color=BLUE, alpha=0.4, width=0.8)
    ax1.plot(x, rolling_avg(durations), color=BLUE, linewidth=2, label="7日均线")
    ax1.set_title("长期用眼时长趋势（分钟/日）")
    ax1.set_ylabel("分钟")
    ax1.set_xticks(x[::tick_step])
    ax1.set_xticklabels(labels[::tick_step], fontsize=7)
    ax1.grid(axis="y")
    ax1.legend(fontsize=8)

    # 良好坐姿率趋势
    ax2 = fig.add_subplot(3, 1, 2)
    ax2.plot(x, good_pct, color=SUB_CLR, linewidth=1, alpha=0.5)
    ax2.plot(x, rolling_avg(good_pct), color=GREEN, linewidth=2, label="7日均线")
    ax2.fill_between(x, rolling_avg(good_pct), alpha=0.15, color=GREEN)
    ax2.axhline(70, color=GREEN, linewidth=1, linestyle="--", alpha=0.6, label="目标70%")
    ax2.set_title("长期良好坐姿率趋势（%）")
    ax2.set_ylabel("%")
    ax2.set_ylim(0, 110)
    ax2.set_xticks(x[::tick_step])
    ax2.set_xticklabels(labels[::tick_step], fontsize=7)
    ax2.grid(axis="y")
    ax2.legend(fontsize=8)

    # 平均视距趋势
    ax3 = fig.add_subplot(3, 1, 3)
    ax3.plot(x, distances, color=SUB_CLR, linewidth=1, alpha=0.5)
    ax3.plot(x, rolling_avg(distances), color=PURPLE, linewidth=2, label="7日均线")
    ax3.fill_between(x, rolling_avg(distances), alpha=0.15, color=PURPLE)
    ax3.axhline(50, color=GREEN, linewidth=1, linestyle="--", alpha=0.6, label="安全50cm")
    ax3.set_title("长期平均视距趋势（cm）")
    ax3.set_ylabel("cm")
    ax3.set_xticks(x[::tick_step])
    ax3.set_xticklabels(labels[::tick_step], fontsize=7)
    ax3.grid(axis="y")
    ax3.legend(fontsize=8)

    return fig


# ── 趋势建议生成 ─────────────────────────────────────────
def _build_stats_summary(longterm_stats: list, user_age: int) -> tuple:
    """计算近7日统计摘要，返回 (数据字典, 给AI看的文字摘要)"""
    recent    = longterm_stats[-7:]
    avg_dur   = float(np.mean([s["total_sec"] for s in recent])) / 60
    avg_good  = float(np.mean([s["good_ratio"] for s in recent]))
    dist_vals = [s["avg_distance"] for s in recent if s.get("avg_distance", 0) > 0]
    avg_dist  = float(np.mean(dist_vals)) if dist_vals else 0.0

    rec_map = {(6, 8): 90, (9, 12): 120, (13, 18): 150}
    daily_limit = 120
    for (lo, hi), lim in rec_map.items():
        if lo <= user_age <= hi:
            daily_limit = lim

    stats = {
        "avg_daily_minutes" : round(avg_dur, 1),
        "daily_limit_minutes": daily_limit,
        "good_posture_pct"  : round(avg_good, 1),
        "avg_distance_cm"   : round(avg_dist, 1),
        "days_analyzed"     : len(recent),
        "user_age"          : user_age,
    }
    summary = (
        f"用户年龄：{user_age}岁，该年龄段建议每日用眼上限：{daily_limit}分钟\n"
        f"近{len(recent)}日平均每日用眼时长：{avg_dur:.1f}分钟\n"
        f"近{len(recent)}日平均良好坐姿率：{avg_good:.1f}%\n"
        f"近{len(recent)}日平均视距：{avg_dist:.1f}cm（安全线：50cm）"
    )
    return stats, summary


def _fallback_advice(stats: dict) -> str:
    """DeepSeek API 不可用时的本地兜底建议"""
    lines = [f"📊 基于近{stats['days_analyzed']}日数据的用眼建议（年龄：{stats['user_age']}岁）\n"]
    avg_dur     = stats["avg_daily_minutes"]
    daily_limit = stats["daily_limit_minutes"]
    avg_good    = stats["good_posture_pct"]
    avg_dist    = stats["avg_distance_cm"]

    if avg_dur > daily_limit:
        lines.append(f"⏱ 用眼时长：日均 {avg_dur:.0f} 分钟，超出建议上限 {daily_limit} 分钟"
                     f" 约 {avg_dur - daily_limit:.0f} 分钟。建议减少非必要屏幕时间，增加户外活动。")
    else:
        lines.append(f"⏱ 用眼时长：日均 {avg_dur:.0f} 分钟，符合年龄建议，继续保持！")

    if avg_good < 50:
        lines.append(f"🪑 坐姿质量：良好率仅 {avg_good:.1f}%，偏低。"
                     "建议检查座椅高度，并开启语音提醒帮助养成习惯。")
    elif avg_good < 70:
        lines.append(f"🪑 坐姿质量：良好率 {avg_good:.1f}%，有改善空间。")
    else:
        lines.append(f"🪑 坐姿质量：良好率 {avg_good:.1f}%，表现优秀！")

    if avg_dist > 0:
        if avg_dist < 40:
            lines.append(f"👁 视距：{avg_dist:.1f}cm，显著偏近，近视风险高！"
                         "请调整屏幕位置并尽快安排视力检查。")
        elif avg_dist < 50:
            lines.append(f"👁 视距：{avg_dist:.1f}cm，略低于安全线50cm，请注意调整。")
        else:
            lines.append(f"👁 视距：{avg_dist:.1f}cm，保持良好。")

    lines.append("\n💡 通用建议：")
    lines.append("  • 每用眼20-30分钟，休息5分钟，望向6米以外放松睫状肌。")
    lines.append("  • 保持充足室内采光，避免在昏暗环境下用眼。")
    lines.append("  • 每天保证1-2小时户外活动，自然光照有助于预防近视。")
    lines.append("  • 每半年到医院进行规范的视力和屈光检查。")
    return "\n".join(lines)


def generate_advice(longterm_stats: list, user_age: int = 10,
                    api_key: str = "") -> str:
    """
    生成个性化用眼建议。
    优先调用 DeepSeek API 生成自然语言建议；若 API 不可用则降级为本地模板。
    """
    if not longterm_stats:
        return "暂无足够数据，请继续使用系统采集数据后查看建议。"

    stats, summary = _build_stats_summary(longterm_stats, user_age)

    # ── 调用 DeepSeek API ─────────────────────────────────
    if api_key and not api_key.startswith("在这里填入"):
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )

            system_prompt = (
                "你是一位专业的儿童视力保健顾问，擅长根据用眼监测数据为家长和孩子提供"
                "科学、温暖、具体可操作的用眼建议。\n"
                "输出要求：\n"
                "1. 使用中文，语气亲切但专业\n"
                "2. 针对数据中的具体问题给出有针对性的建议，而非泛泛而谈\n"
                "3. 按「用眼时长」「坐姿质量」「视距」「综合建议」四个板块组织内容\n"
                "4. 每个板块开头用对应 emoji（⏱🪑👁💡）\n"
                "5. 总长度控制在300字以内，突出最重要的2-3个改善点\n"
                "6. 若某项数据表现良好，简短肯定后重点放在需要改善的项目上"
            )
            user_prompt = (
                f"以下是该儿童近期的用眼监测数据摘要，请生成个性化建议：\n\n"
                f"{summary}\n\n"
                f"请根据以上数据，重点分析问题所在，给出具体可操作的改善建议。"
            )

            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=600,
                temperature=0.7,
            )
            ai_text = resp.choices[0].message.content.strip()
            return f"🤖 AI 个性化建议（基于近{stats['days_analyzed']}日数据）\n\n{ai_text}"

        except ImportError:
            return (_fallback_advice(stats) +
                    "\n\n⚠ 提示：请运行 pip install openai 后重启程序以启用 AI 建议。")
        except Exception as e:
            return (_fallback_advice(stats) +
                    f"\n\n⚠ AI 建议暂时不可用（{e}），已显示本地建议。")

    # ── 无有效 API Key：本地兜底 ─────────────────────────
    return _fallback_advice(stats)