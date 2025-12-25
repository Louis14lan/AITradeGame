"""
测试K线数据获取功能
验证从交易所API获取真实的1h、4h K线数据
"""
from market_data import MarketDataFetcher


def test_kline_data():
    """测试K线数据获取"""
    fetcher = MarketDataFetcher()

    coin = 'BTC'

    print(f"\n{'='*60}")
    print(f"测试 {coin} 的K线数据获取")
    print(f"{'='*60}\n")

    # 测试1小时K线
    print("1. 获取1小时K线数据 (最近2根):")
    kline_1h = fetcher.get_kline_data(coin, '1h', 2)
    if kline_1h:
        print(f"   成功获取 {len(kline_1h)} 根1小时K线")
        for i, candle in enumerate(kline_1h):
            print(f"   [{i}] 时间: {candle['timestamp']}, "
                  f"开: {candle['open']:.2f}, "
                  f"高: {candle['high']:.2f}, "
                  f"低: {candle['low']:.2f}, "
                  f"收: {candle['close']:.2f}, "
                  f"量: {candle['volume']:.2f}")
        if len(kline_1h) >= 2:
            change_1h = ((kline_1h[-1]['close'] - kline_1h[-2]['close']) / kline_1h[-2]['close'] * 100)
            print(f"   1小时涨跌幅: {change_1h:+.2f}%")
    else:
        print("   ❌ 获取失败")

    # 测试4小时K线
    print("\n2. 获取4小时K线数据 (最近2根):")
    kline_4h = fetcher.get_kline_data(coin, '4h', 2)
    if kline_4h:
        print(f"   成功获取 {len(kline_4h)} 根4小时K线")
        for i, candle in enumerate(kline_4h):
            print(f"   [{i}] 时间: {candle['timestamp']}, "
                  f"开: {candle['open']:.2f}, "
                  f"高: {candle['high']:.2f}, "
                  f"低: {candle['low']:.2f}, "
                  f"收: {candle['close']:.2f}, "
                  f"量: {candle['volume']:.2f}")
        if len(kline_4h) >= 2:
            change_4h = ((kline_4h[-1]['close'] - kline_4h[-2]['close']) / kline_4h[-2]['close'] * 100)
            print(f"   4小时涨跌幅: {change_4h:+.2f}%")
    else:
        print("   ❌ 获取失败")

    # 测试日线K线
    print("\n3. 获取日线K线数据 (最近8根):")
    kline_1d = fetcher.get_kline_data(coin, '1d', 8)
    if kline_1d:
        print(f"   成功获取 {len(kline_1d)} 根日线K线")
        if len(kline_1d) >= 2:
            change_24h = ((kline_1d[-1]['close'] - kline_1d[-2]['close']) / kline_1d[-2]['close'] * 100)
            print(f"   24小时涨跌幅: {change_24h:+.2f}%")
        if len(kline_1d) >= 8:
            change_7d = ((kline_1d[-1]['close'] - kline_1d[-8]['close']) / kline_1d[-8]['close'] * 100)
            print(f"   7天涨跌幅: {change_7d:+.2f}%")
    else:
        print("   ❌ 获取失败")

    # 测试技术指标计算（包含新的价格变化计算）
    print("\n4. 测试技术指标计算（使用真实K线数据）:")
    indicators = fetcher.calculate_technical_indicators(coin)
    if indicators:
        print(f"   当前价格: ${indicators.get('current_price', 0):.2f}")
        print(f"   1小时涨跌: {indicators.get('change_1h', 0):+.2f}%")
        print(f"   4小时涨跌: {indicators.get('change_4h', 0):+.2f}%")
        print(f"   24小时涨跌: {indicators.get('change_24h', 0):+.2f}%")
        print(f"   7天涨跌: {indicators.get('change_7d', 0):+.2f}%")
        print(f"   RSI(14): {indicators.get('rsi_14', 0):.2f}")
        print(f"   趋势方向: {indicators.get('trend_direction', 'unknown')}")
    else:
        print("   ❌ 计算失败")

    print(f"\n{'='*60}")
    print("测试完成")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    test_kline_data()
