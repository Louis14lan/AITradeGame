#!/usr/bin/env python3
"""测试量价指标系统"""

from market_data import MarketDataFetcher
from ai_trader import AITrader

def test_volume_indicators():
    """测试成交量指标计算"""
    print('=' * 70)
    print('测试量价指标系统')
    print('=' * 70)
    print()

    # 测试技术指标（包括成交量）
    print('=== 测试成交量指标计算 ===')
    fetcher = MarketDataFetcher()
    indicators = fetcher.calculate_technical_indicators('BTC')

    if indicators:
        print('✓ 技术指标计算成功')
        print(f'  总指标数: {len(indicators)}')
        print()

        # 检查成交量指标
        volume_indicators = [
            'volume_24h', 'volume_ma_5', 'volume_ma_20',
            'volume_ratio', 'obv', 'volume_trend',
            'price_volume_divergence'
        ]

        print('  成交量指标检查:')
        for ind in volume_indicators:
            if ind in indicators:
                value = indicators[ind]
                if isinstance(value, float):
                    if ind.startswith('volume_') and not ind.endswith(('_ratio', '_trend', '_divergence')):
                        print(f'    ✓ {ind}: ${value:,.0f}')
                    elif ind == 'volume_ratio':
                        print(f'    ✓ {ind}: {value:.2f}x')
                    elif ind == 'obv':
                        print(f'    ✓ {ind}: {value:,.0f}')
                    else:
                        print(f'    ✓ {ind}: {value:.2f}')
                else:
                    print(f'    ✓ {ind}: {value}')
            else:
                print(f'    ✗ {ind}: 缺失')

        print()
        print('  关键量价信息:')
        print(f'    当前24h成交量: ${indicators.get("volume_24h", 0):,.0f}')
        print(f'    20日平均成交量: ${indicators.get("volume_ma_20", 0):,.0f}')
        print(f'    量比 (Volume Ratio): {indicators.get("volume_ratio", 0):.2f}x')

        volume_ratio = indicators.get('volume_ratio', 1.0)
        if volume_ratio > 1.5:
            volume_status = "高量能 (看涨确认)"
        elif volume_ratio < 0.5:
            volume_status = "低量能 (趋势疲弱)"
        else:
            volume_status = "正常量能"
        print(f'    量能状态: {volume_status}')

        print(f'    成交量趋势: {indicators.get("volume_trend", "stable")}')

        pv_div = indicators.get('price_volume_divergence', 'none')
        if pv_div != 'none':
            print(f'    ⚠️  量价背离: {pv_div} (可能反转信号)')
        else:
            print(f'    量价背离: 无')

    else:
        print('✗ 技术指标计算失败')
        return

    # 测试 Prompt 构建
    print()
    print('=== 测试量价 Prompt 构建 ===')

    market_state = {
        'BTC': {
            'price': indicators.get('current_price', 97000),
            'change_24h': 2.5,
            'indicators': indicators
        }
    }

    portfolio = {
        'total_value': 10000,
        'cash': 5000,
        'positions': []
    }

    account_info = {
        'initial_capital': 10000,
        'total_return': 0,
        'current_time': '2025-01-01 00:00:00'
    }

    trader = AITrader('openai', 'test-key', 'http://test.com', 'test-model')
    prompt = trader._build_prompt(market_state, portfolio, account_info)

    if prompt:
        print('✓ Prompt 构建成功')
        print(f'  Prompt 总长度: {len(prompt)} 字符')

        # 检查量价相关内容
        volume_checks = {
            '包含 Volume': 'Volume' in prompt,
            '包含量比 (Ratio)': 'Ratio' in prompt,
            '包含量能趋势': 'Volume Trend' in prompt or 'INCREASING' in prompt or 'DECREASING' in prompt,
            '包含量价指导': 'Volume Analysis Guidelines' in prompt,
            '包含量价背离': 'Price-Volume' in prompt or 'DIVERGENCE' in prompt,
        }

        print('\n  量价内容检查:')
        for check_name, result in volume_checks.items():
            status = '✓' if result else '✗'
            print(f'    {status} {check_name}')

        # 显示量价部分的 Prompt 预览
        print('\n  量价分析部分预览:')
        print('  ' + '-' * 60)
        lines = prompt.split('\n')
        volume_section_started = False
        preview_lines = []

        for line in lines:
            if 'Volume' in line:
                volume_section_started = True
            if volume_section_started:
                preview_lines.append(line)
                if len(preview_lines) >= 5:
                    break

        for line in preview_lines[:5]:
            print(f'  {line}')
        print('  ' + '-' * 60)

    else:
        print('✗ Prompt 构建失败')

    print()
    print('=' * 70)
    print('量价指标系统测试完成！')
    print('=' * 70)

if __name__ == '__main__':
    try:
        test_volume_indicators()
    except Exception as e:
        print(f'\n✗ 测试过程中出现错误: {e}')
        import traceback
        traceback.print_exc()
