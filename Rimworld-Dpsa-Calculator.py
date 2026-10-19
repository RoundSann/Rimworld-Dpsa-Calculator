# -*- coding: utf-8 -*-
"""
远程武器 DPS / DPSA 游戏外计算脚本
=====================================
计算逻辑与 WeaponStatsExpanded (C#) 完全一致：
  - 品质 : 影响伤害 (RangedWeapon_DamageMultiplier) 和命中率 (AccuracyX 的 StatPart_Quality)
  - DPS  : CalculateAdjustedDps
  - DPSA : RecalculateAllRangeDpsaWithRangeCheck
  - 护甲 : CalculateExpectedArmorMultiplier (多层 = 单层 ^ 层数)

用法：只修改下面【设置区】的变量，然后运行脚本即可。
"""

# ============================================================
# 设置区 —— 在这里修改输入变量
# ============================================================

# ---- 武器基础属性（对应游戏内武器 def 的数值）----
WARMUP                    = 1    # 瞄准时间 warmupTime (秒)
COOLDOWN                  = 2    # 冷却时间 range cooldownTime (秒)
MAX_RANGE                 = 26      #最大射程
TICKS_BETWEEN_BURST_SHOTS = 12      # 连发间隔 (ticks)
BURST_SHOT_COUNT          = 5     # 连发数 burstShotCount
DAMAGE                    = 14     # 单发伤害 (projectile damageAmountBase)

MIN_RANGE                 = 0       #最小射程
ARMOR_PENETRATION         = 11     # 穿甲 (百分比，输入 15 表示 15%)
# ---- 命中率（各射程距离命中率，0~100，单位 %）----
ACCURACY_TOUCH   = 70   # 贴身 (3格)
ACCURACY_SHORT   = 84   # 近距 (12格)
ACCURACY_MEDIUM  = 75   # 中距 (25格)
ACCURACY_LONG    = 65   # 远距 (40格)


# ---- 扩展 mod 的模拟设置 ----
QUALITY               = 4     # 品质：-2极差 -1较差 0一般 1良好 2极佳 3大师 4传奇
AIMING_TIME_FACTOR    = 1   # 瞄准时间系数 (百分比：100 / 50 / 10 / 1)
SELECTED_ARMOR_RATING = 0     # 目标护甲值 (百分比，输入 100 表示 100%)
SELECTED_ARMOR_LAYERS = 1     # 护甲层数

# ============================================================
# 以下为计算逻辑，无需修改
# ============================================================

TPS = 60  # ticks per second

# 射程距离常量（与 C# 中 RNG_TOUCH/SHORT/MEDIUM/LONG 一致）
RNG_TOUCH  = 3
RNG_SHORT  = 12
RNG_MEDIUM = 25
RNG_LONG   = 40

# 品质等级名称（-2 ~ 4）
QUALITY_NAMES = {
    -2: "极差 (Awful)",
    -1: "较差 (Poor)",
    0:  "一般 (Normal)",
    1:  "良好 (Good)",
    2:  "极佳 (Excellent)",
    3:  "大师 (Masterwork)",
    4:  "传奇 (Legendary)",
}

# 品质对伤害的乘数（RangedWeapon_DamageMultiplier 的 StatPart_Quality）
QUALITY_DAMAGE_FACTOR = {
    -2: 0.9,
    -1: 1.0,
    0:  1.0,
    1:  1.0,
    2:  1.0,
    3:  1.25,
    4:  1.5,
}

# 品质对命中率的乘数（AccuracyX 的 StatPart_Quality）
QUALITY_ACCURACY_FACTOR = {
    -2: 0.8,
    -1: 0.9,
    0:  1.0,
    1:  1.1,
    2:  1.2,
    3:  1.35,
    4:  1.5,
}

# 命中率上下限（AccuracyBase: maxValue 1, minValue 0.01）
ACCURACY_MAX = 100.0
ACCURACY_MIN = 1.0


def round_half_to_even(value):
    """对应 C# Mathf.RoundToInt（四舍六入五成双）。"""
    return int(round(value))


def apply_quality_to_accuracy(accuracy, quality_factor):
    """品质系数应用到命中率并裁剪到 [1%, 100%]。命中率为 0 表示该射程无效，保持 0。"""
    if accuracy <= 0:
        return 0.0
    adjusted = accuracy * quality_factor
    if adjusted > ACCURACY_MAX:
        adjusted = ACCURACY_MAX
    if adjusted < ACCURACY_MIN:
        adjusted = ACCURACY_MIN
    return adjusted


def calculate_single_layer_armor_multiplier(armor_rating, armor_penetration):
    """单层护甲的期望伤害乘数，基于原版 ArmorUtility.ApplyArmor。"""
    effective_armor = max(armor_rating - armor_penetration, 0.0)
    if effective_armor >= 2.0:
        return 0.0
    if effective_armor >= 1.0:
        return 0.5 - 0.25 * effective_armor
    return 1.0 - 0.75 * effective_armor


def calculate_expected_armor_multiplier(armor_rating, armor_penetration, layers):
    """多层护甲期望乘数 = 单层乘数 ^ 层数。"""
    single_layer = calculate_single_layer_armor_multiplier(armor_rating, armor_penetration)
    layers = max(layers, 1)
    if layers == 1:
        return single_layer
    return single_layer ** layers


def calculate_adjusted_dps(damage, cooldown, warmup, burst_shot_count, ticks_between_burst_shots):
    """对应 C# CalculateAdjustedDps。"""
    burst_damage = damage * burst_shot_count
    warmup_ticks = (cooldown + warmup) * TPS
    burst_ticks = (burst_shot_count - 1) * ticks_between_burst_shots
    total_time = (warmup_ticks + burst_ticks) / TPS
    if total_time <= 0:
        return 0.0
    return round(burst_damage / total_time, 2)


def calculate_dpsa(dps, min_range, max_range,
                   acc_touch, acc_short, acc_medium, acc_long):
    """对应 C# RecalculateAllRangeDpsaWithRangeCheck。
    返回 (dpsa_touch, dpsa_short, dpsa_medium, dpsa_long, dpsa_avg)。"""
    dpsa_touch = dpsa_short = dpsa_medium = dpsa_long = 0.0
    sum_accuracy = 0.0
    num_accuracy = 0

    if min_range <= RNG_TOUCH <= max_range and acc_touch > 0:
        dpsa_touch = round(dps * acc_touch / 100.0, 1)
        sum_accuracy += acc_touch
        num_accuracy += 1

    if min_range <= RNG_SHORT <= max_range and acc_short > 0:
        dpsa_short = round(dps * acc_short / 100.0, 1)
        sum_accuracy += acc_short
        num_accuracy += 1

    if min_range <= RNG_MEDIUM <= max_range and acc_medium > 0:
        dpsa_medium = round(dps * acc_medium / 100.0, 1)
        sum_accuracy += acc_medium
        num_accuracy += 1

    if min_range <= RNG_LONG <= max_range and acc_long > 0:
        dpsa_long = round(dps * acc_long / 100.0, 1)
        sum_accuracy += acc_long
        num_accuracy += 1

    dpsa_avg = round(dps * (sum_accuracy / num_accuracy) / 100.0, 1) if num_accuracy > 0 else 0.0
    return dpsa_touch, dpsa_short, dpsa_medium, dpsa_long, dpsa_avg


def main():
    # 输入换算：百分比 -> 小数
    armor_penetration = ARMOR_PENETRATION / 100.0
    armor_rating = SELECTED_ARMOR_RATING / 100.0
    aiming_time_factor = AIMING_TIME_FACTOR / 100.0

    quality_damage_factor = QUALITY_DAMAGE_FACTOR.get(QUALITY, 1.0)
    quality_accuracy_factor = QUALITY_ACCURACY_FACTOR.get(QUALITY, 1.0)

    # 1) 品质影响伤害（对应 C# GetDamageAmount: RoundToInt(damageBase * damageMultiplier)）
    quality_damage = round_half_to_even(DAMAGE * quality_damage_factor)

    # 2) 护甲乘数应用到伤害（对应 C# CompletelyReplaceRangedWeaponProperties）
    armor_multiplier = calculate_expected_armor_multiplier(
        armor_rating, armor_penetration, SELECTED_ARMOR_LAYERS)
    effective_damage = round(quality_damage * armor_multiplier, 2)

    # 3) 瞄准时间系数应用到 warmup
    adjusted_warmup = WARMUP * aiming_time_factor

    # 4) 计算 DPS
    dps = 0.0
    if COOLDOWN > 0:
        dps = calculate_adjusted_dps(
            effective_damage, COOLDOWN, adjusted_warmup,
            BURST_SHOT_COUNT, TICKS_BETWEEN_BURST_SHOTS)

    # 5) 品质系数应用到命中率
    acc_touch  = apply_quality_to_accuracy(ACCURACY_TOUCH, quality_accuracy_factor)
    acc_short  = apply_quality_to_accuracy(ACCURACY_SHORT, quality_accuracy_factor)
    acc_medium = apply_quality_to_accuracy(ACCURACY_MEDIUM, quality_accuracy_factor)
    acc_long   = apply_quality_to_accuracy(ACCURACY_LONG, quality_accuracy_factor)

    # 6) 计算 DPSA
    dpsa_touch, dpsa_short, dpsa_medium, dpsa_long, dpsa_avg = calculate_dpsa(
        dps, MIN_RANGE, MAX_RANGE,
        acc_touch, acc_short, acc_medium, acc_long)

    # ---- 输出 ----
    print("[结果]")
    print("  DPS             : {0}".format(dps))
    print("  DPSA (贴身 3格) : {0}".format(dpsa_touch))
    print("  DPSA (近距12格) : {0}".format(dpsa_short))
    print("  DPSA (中距25格) : {0}".format(dpsa_medium))
    print("  DPSA (远距40格) : {0}".format(dpsa_long))
    print("  DPSA (平均)     : {0}".format(dpsa_avg))


if __name__ == "__main__":
    main()
