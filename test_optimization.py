#!/usr/bin/env python3
"""测试优化后的技术指标和 Prompt 构建系统"""

from market_data import MarketDataFetcher
from ai_trader import AITrader

def test_technical_indicators():
    """测试技术指标计算"""
    print('=== 测试技术指标计算 ===')
    fetcher = MarketDataFetcher()
    indicators = fetcher.calculate_technical_indicators('BTC')

    if indicators:
        print('✓ 技术指标计算成功')
        print(f'  包含字段数: {len(indicators)}')

        # 检查关键指标
        key_indicators = ['ema_9', 'ema_21', 'ema_50', 'macd', 'rsi_14',
                         'stoch_rsi', 'roc_10', 'atr_14', 'bb_upper',
                         'trend_direction', 'trend_strength', 'volatility_level']

        missing = [ind for ind in key_indicators if ind not in indicators]
        if not missing:
            print('✓ 所有关键指标都已计算')
        else:
            print(f'✗ 缺失指标: {missing}')

        print(f'\n  当前价格: ${indicators.get("current_price", 0):,.2f}')
        print(f'  趋势方向: {indicators.get("trend_direction")}')
        print(f'  趋势强度: {indicators.get("trend_strength", 0):.2f}')
        print(f'  波动率水平: {indicators.get("volatility_level")}')
        print(f'  RSI(14): {indicators.get("rsi_14", 0):.2f}')
        print(f'  MACD: {indicators.get("macd", 0):.2f}')
    else:
        print('✗ 技术指标计算失败')

    return indicators

def test_prompt_building(indicators):
    """测试 Prompt 构建"""
    print('\n=== 测试 Prompt 构建 ===')

    # 模拟市场数据
    market_state = {
        'BTC': {
            'price': 97000,
            'change_24h': 2.5,
            'indicators': indicators
        },
        'ETH': {
            'price': 3600,
            'change_24h': 1.8,
            'indicators': {
                'current_price': 3600,
                'ema_9': 3580,
                'ema_21': 3550,
                'ema_50': 3500,
                'macd': 15,
                'macd_signal': 12,
                'macd_histogram': 3,
                'rsi_14': 65,
                'stoch_rsi': 70,
                'roc_10': 5.2,
                'atr_14': 50,
                'bb_upper': 3700,
                'bb_middle': 3600,
                'bb_lower': 3500,
                'bb_width': 5.5,
                'change_1h': 0.5,
                'change_4h': 1.2,
                'change_24h': 1.8,
                'change_7d': 8.5,
                'trend_strength': 45,
                'trend_direction': 'bullish',
                'price_position': 'middle',
                'volatility_level': 'medium',
            }
        }
    }

    portfolio = {
        'total_value': 10000,
        'cash': 5000,
        'positions': [
            {
                'coin': 'BTC',
                'side': 'long',
                'quantity': 0.05,
                'avg_price': 95000,
                'leverage': 5,
                'unrealized_pnl': 100,
                'unrealized_pnl_pct': 1.05
            }
        ]
    }

    account_info = {
        'initial_capital': 10000,
        'total_return': 0,
        'current_time': '2025-01-01 00:00:00'
    }

    # 测试 prompt 构建
    trader = AITrader('openai', 'test-key', 'http://test.com', 'test-model')
    prompt = trader._build_prompt(market_state, portfolio, account_info)

    if prompt:
        print('✓ Prompt 构建成功')
        print(f'  Prompt 长度: {len(prompt)} 字符')

        # 检查关键部分
        checks = {
            'MARKET OVERVIEW': 'MARKET OVERVIEW' in prompt,
            'DETAILED MARKET DATA': 'DETAILED MARKET DATA' in prompt,
            'ACCOUNT & POSITIONS': 'ACCOUNT & POSITIONS' in prompt,
            'TRADING FRAMEWORK': 'TRADING FRAMEWORK' in prompt,
            '包含 EMA': 'EMA' in prompt,
            '包含 MACD': 'MACD' in prompt,
            '包含 RSI': 'RSI' in prompt,
            '包含 Bollinger': 'Bollinger' in prompt,
            '包含趋势分析': 'Trend:' in prompt,
            '包含波动率': 'Volatility:' in prompt,
        }

        print('\n  结构完整性检查:')
        for check_name, result in checks.items():
            status = '✓' if result else '✗'
            print(f'    {status} {check_name}')

        # 显示 Prompt 预览
        print('\n  Prompt 预览 (前 500 字符):')
        print('  ' + '-' * 60)
        preview = prompt[:500].replace('\n', '\n  ')
        print(f'  {preview}...')
        print('  ' + '-' * 60)

    else:
        print('✗ Prompt 构建失败')

def main():
    """主测试函数"""
    print('开始测试优化后的 AI 交易系统...\n')

    try:
        # 测试技术指标
        indicators = test_technical_indicators()

        # 测试 Prompt 构建
        if indicators:
            test_prompt_building(indicators)

        print('\n' + '=' * 70)
        print('测试完成！')
        print('=' * 70)

    except Exception as e:
        print(f'\n✗ 测试过程中出现错误: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
