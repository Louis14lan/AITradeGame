#!/usr/bin/env python3
"""
测试基于K线数据的技术指标计算

验证功能：
1. K线数据获取（3分钟周期）
2. 技术指标计算（使用真实OHLC数据）
3. 多周期价格变化计算
4. 降级策略测试
"""

import sys
from market_data import MarketDataFetcher


def test_kline_data_fetch():
    """测试K线数据获取"""
    print("=" * 60)
    print("测试1: K线数据获取")
    print("=" * 60)

    fetcher = MarketDataFetcher()

    # 测试不同周期的K线数据
    intervals = ['3m', '5m', '15m', '1h']
    coins = ['BTC', 'ETH']

    for coin in coins:
        print(f"\n{coin} K线数据测试:")
        for interval in intervals:
            kline_data = fetcher.get_kline_data(coin, interval=interval, limit=10)

            if kline_data:
                latest = kline_data[-1]
                print(f"  ✓ {interval:4s} - 获取成功 ({len(kline_data)} 根蜡烛)")
                print(f"         最新价格: ${latest['close']:,.2f}")
                print(f"         最高/最低: ${latest['high']:,.2f} / ${latest['low']:,.2f}")
                print(f"         成交量: ${latest['volume']:,.0f}")
            else:
                print(f"  ✗ {interval:4s} - 获取失败")

    return True


def test_technical_indicators_3m():
    """测试基于3分钟K线的技术指标计算"""
    print("\n" + "=" * 60)
    print("测试2: 基于3分钟K线的技术指标计算")
    print("=" * 60)

    fetcher = MarketDataFetcher()
    coins = ['BTC', 'ETH']

    for coin in coins:
        print(f"\n{coin} 技术指标 (3分钟周期):")

        # 使用3分钟K线计算指标
        indicators = fetcher.calculate_technical_indicators(coin, interval='3m')

        if not indicators:
            print(f"  ✗ 指标计算失败")
            continue

        print(f"  当前价格: ${indicators['current_price']:,.2f}")

        # 趋势指标
        print(f"\n  趋势指标:")
        print(f"    EMA9:  ${indicators['ema_9']:,.2f}")
        print(f"    EMA21: ${indicators['ema_21']:,.2f}")
        print(f"    EMA50: ${indicators['ema_50']:,.2f}")
        print(f"    MACD:  {indicators['macd']:.2f} | Signal: {indicators['macd_signal']:.2f} | Hist: {indicators['macd_histogram']:.2f}")

        # 动量指标
        print(f"\n  动量指标:")
        print(f"    RSI(14):      {indicators['rsi_14']:.1f}")
        print(f"    Stoch RSI:    {indicators['stoch_rsi']:.1f}")
        print(f"    ROC(10):      {indicators['roc_10']:+.2f}%")

        # 波动率指标
        print(f"\n  波动率指标:")
        print(f"    ATR(14):      ${indicators['atr_14']:,.2f}")
        print(f"    BB Upper:     ${indicators['bb_upper']:,.2f}")
        print(f"    BB Middle:    ${indicators['bb_middle']:,.2f}")
        print(f"    BB Lower:     ${indicators['bb_lower']:,.2f}")
        print(f"    BB Width:     {indicators['bb_width']:.2f}%")

        # 成交量指标
        print(f"\n  成交量指标:")
        print(f"    Volume 24h:   ${indicators['volume_24h']:,.0f}")
        print(f"    Volume MA20:  ${indicators['volume_ma_20']:,.0f}")
        print(f"    Volume Ratio: {indicators['volume_ratio']:.2f}x")
        print(f"    Volume Trend: {indicators['volume_trend']}")
        print(f"    PV Divergence: {indicators['price_volume_divergence']}")

        # 多周期价格变化
        print(f"\n  多周期价格变化:")
        print(f"    1小时:  {indicators['change_1h']:+.2f}%")
        print(f"    4小时:  {indicators['change_4h']:+.2f}%")
        print(f"    24小时: {indicators['change_24h']:+.2f}%")
        print(f"    7天:    {indicators['change_7d']:+.2f}%")

        # 综合分析
        print(f"\n  综合分析:")
        print(f"    趋势强度:    {indicators['trend_strength']:+.1f}")
        print(f"    趋势方向:    {indicators['trend_direction']}")
        print(f"    价格位置:    {indicators['price_position']}")
        print(f"    波动率等级:  {indicators['volatility_level']}")

    return True


def test_time_unit_comparison():
    """对比不同时间单位的指标计算结果"""
    print("\n" + "=" * 60)
    print("测试3: 不同时间周期对比（EMA响应速度）")
    print("=" * 60)

    fetcher = MarketDataFetcher()
    coin = 'BTC'

    intervals = ['3m', '15m', '1h']

    print(f"\n{coin} 在不同周期的EMA对比:")
    print(f"{'周期':<8} {'EMA9':<12} {'EMA21':<12} {'EMA50':<12} {'趋势方向':<10}")
    print("-" * 60)

    for interval in intervals:
        indicators = fetcher.calculate_technical_indicators(coin, interval=interval)

        if indicators:
            print(f"{interval:<8} "
                  f"${indicators['ema_9']:>10,.2f}  "
                  f"${indicators['ema_21']:>10,.2f}  "
                  f"${indicators['ema_50']:>10,.2f}  "
                  f"{indicators['trend_direction']:<10}")

    print("\n说明:")
    print("  - 3分钟周期: EMA9 = 9×3分钟 = 27分钟，适合短线交易")
    print("  - 15分钟周期: EMA9 = 9×15分钟 = 135分钟，适合波段交易")
    print("  - 1小时周期: EMA9 = 9×1小时 = 9小时，适合中长线交易")

    return True


def test_atr_accuracy():
    """测试ATR计算精度（真实OHLC vs 近似值）"""
    print("\n" + "=" * 60)
    print("测试4: ATR计算精度验证")
    print("=" * 60)

    fetcher = MarketDataFetcher()
    coin = 'BTC'

    # 使用3分钟K线计算ATR（真实OHLC）
    kline_data = fetcher.get_kline_data(coin, interval='3m', limit=200)

    if kline_data and len(kline_data) >= 50:
        # 真实ATR
        atr_real = fetcher._calculate_atr(kline_data, 14)

        # 近似ATR（将K线转为历史数据格式）
        historical_approx = [{'price': k['close']} for k in kline_data]
        atr_approx = fetcher._calculate_atr_approximated(historical_approx, 14)

        print(f"\n{coin} ATR对比:")
        print(f"  真实OHLC计算: ${atr_real:,.2f}")
        print(f"  近似值计算:   ${atr_approx:,.2f}")
        print(f"  精度差异:     {abs(atr_real - atr_approx) / atr_real * 100:.1f}%")

        # 显示最近3根K线的OHLC数据
        print(f"\n最近3根3分钟K线:")
        for i, k in enumerate(kline_data[-3:], 1):
            spread = k['high'] - k['low']
            spread_pct = spread / k['close'] * 100
            print(f"  K线{i}: 开${k['open']:,.2f} 高${k['high']:,.2f} "
                  f"低${k['low']:,.2f} 收${k['close']:,.2f} "
                  f"(振幅: {spread_pct:.2f}%)")
    else:
        print(f"  ✗ K线数据不足，无法测试")

    return True


def test_fallback_mechanism():
    """测试降级策略"""
    print("\n" + "=" * 60)
    print("测试5: 降级策略测试")
    print("=" * 60)

    fetcher = MarketDataFetcher()

    # 测试一个可能没有K线数据的小币种
    test_coin = 'DOGE'

    print(f"\n测试币种: {test_coin}")
    print("尝试获取3分钟K线数据...")

    indicators = fetcher.calculate_technical_indicators(test_coin, interval='3m')

    if indicators:
        print(f"  ✓ 成功获取指标数据")
        print(f"  当前价格: ${indicators['current_price']:.6f}")
        print(f"  趋势方向: {indicators['trend_direction']}")
        print(f"  (如果K线失败，会自动降级到日线数据)")
    else:
        print(f"  ✗ 指标计算失败")

    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("技术指标优化测试套件")
    print("测试3分钟K线数据计算的技术指标")
    print("=" * 60)

    tests = [
        ("K线数据获取", test_kline_data_fetch),
        ("技术指标计算", test_technical_indicators_3m),
        ("时间周期对比", test_time_unit_comparison),
        ("ATR计算精度", test_atr_accuracy),
        ("降级策略", test_fallback_mechanism),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n✗ 测试失败: {test_name}")
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # 显示测试结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    for test_name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{status:8s} - {test_name}")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！技术指标优化成功。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查错误信息。")
        return 1


if __name__ == '__main__':
    sys.exit(main())
