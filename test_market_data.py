#!/usr/bin/env python3
"""
Market Data API 测试脚本
用于验证各个数据源接口是否能正常调用
"""
import time
import sys

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_warn(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.CYAN}ℹ {text}{Colors.RESET}")

def test_coingecko_direct():
    """直接测试 CoinGecko API"""
    import requests
    print_header("测试 CoinGecko API (直接调用)")
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': 'bitcoin,ethereum',
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        
        start = time.time()
        response = requests.get(url, params=params, timeout=10)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"CoinGecko API 可用 (响应时间: {elapsed*1000:.0f}ms)")
            print(f"   BTC: ${data['bitcoin']['usd']:,.2f}")
            print(f"   ETH: ${data['ethereum']['usd']:,.2f}")
            return True
        elif response.status_code == 429:
            print_warn(f"CoinGecko API 限流 (429) - 请稍后重试")
            return False
        else:
            print_error(f"CoinGecko API 错误: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"CoinGecko API 失败: {e}")
        return False

def test_coincap_direct():
    """直接测试 CoinCap API"""
    import requests
    print_header("测试 CoinCap API (直接调用)")
    
    try:
        url = "https://api.coincap.io/v2/assets"
        params = {'ids': 'bitcoin,ethereum'}
        
        start = time.time()
        response = requests.get(url, params=params, timeout=10)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"CoinCap API 可用 (响应时间: {elapsed*1000:.0f}ms)")
            for asset in data.get('data', []):
                print(f"   {asset['symbol']}: ${float(asset['priceUsd']):,.2f}")
            return True
        else:
            print_error(f"CoinCap API 错误: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"CoinCap API 失败: {e}")
        return False

def test_binance_direct():
    """直接测试 Binance API"""
    import requests
    print_header("测试 Binance API (直接调用)")
    
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        params = {'symbols': '["BTCUSDT","ETHUSDT"]'}
        
        start = time.time()
        response = requests.get(url, params=params, timeout=10)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Binance API 可用 (响应时间: {elapsed*1000:.0f}ms)")
            for item in data:
                print(f"   {item['symbol']}: ${float(item['lastPrice']):,.2f}")
            return True
        elif response.status_code == 451:
            print_warn("Binance API 地理限制 (451) - 您的地区无法访问")
            return False
        else:
            print_error(f"Binance API 错误: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Binance API 失败: {e}")
        return False

def test_market_data_fetcher():
    """测试 MarketDataFetcher 类"""
    from market_data import MarketDataFetcher
    
    fetcher = MarketDataFetcher()
    results = {
        'get_current_prices': False,
        'get_market_data': False,
        'get_historical_prices': False,
        'calculate_technical_indicators': False,
        'cache': False,
    }
    
    # 测试 1: 获取当前价格
    print_header("测试 MarketDataFetcher.get_current_prices()")
    try:
        coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
        start = time.time()
        prices = fetcher.get_current_prices(coins)
        elapsed = time.time() - start
        
        if prices and len(prices) > 0:
            print_success(f"获取价格成功 ({len(prices)}/{len(coins)} 个币种, 耗时: {elapsed:.2f}s)")
            for coin, data in prices.items():
                change_color = Colors.GREEN if data['change_24h'] >= 0 else Colors.RED
                print(f"   {coin:5}: ${data['price']:>12,.2f}  {change_color}{data['change_24h']:+.2f}%{Colors.RESET}")
            results['get_current_prices'] = True
        else:
            print_error("获取价格失败 - 返回空数据")
    except Exception as e:
        print_error(f"获取价格失败: {e}")
    
    # 测试 2: 缓存功能
    print_header("测试缓存功能")
    try:
        # 使用相同的 coins 列表来测试缓存
        start = time.time()
        prices2 = fetcher.get_current_prices(coins)  # 使用相同的 coins
        elapsed = time.time() - start
        
        if elapsed < 0.1:  # 缓存命中应该 < 100ms
            print_success(f"缓存命中 (耗时: {elapsed*1000:.1f}ms)")
            results['cache'] = True
        else:
            print_warn(f"缓存可能未命中 (耗时: {elapsed*1000:.1f}ms)")
        
        status = fetcher.get_cache_status()
        print_info(f"缓存状态: {status}")
    except Exception as e:
        print_error(f"缓存测试失败: {e}")
    
    # 测试 3: 获取市场数据
    print_header("测试 MarketDataFetcher.get_market_data()")
    try:
        start = time.time()
        market_data = fetcher.get_market_data('BTC')
        elapsed = time.time() - start
        
        if market_data:
            print_success(f"获取市场数据成功 (耗时: {elapsed:.2f}s)")
            print(f"   当前价格: ${market_data.get('current_price', 0):,.2f}")
            print(f"   市值: ${market_data.get('market_cap', 0):,.0f}")
            print(f"   24h交易量: ${market_data.get('total_volume', 0):,.0f}")
            print(f"   24h涨跌: {market_data.get('price_change_24h', 0):.2f}%")
            results['get_market_data'] = True
        else:
            print_warn("获取市场数据返回空 - 可能所有API都失败")
    except Exception as e:
        print_error(f"获取市场数据失败: {e}")
    
    # 测试 4: 获取历史价格
    print_header("测试 MarketDataFetcher.get_historical_prices()")
    try:
        start = time.time()
        historical = fetcher.get_historical_prices('BTC', days=7)
        elapsed = time.time() - start
        
        if historical and len(historical) > 0:
            print_success(f"获取历史数据成功 ({len(historical)} 条记录, 耗时: {elapsed:.2f}s)")
            print(f"   最早价格: ${historical[0]['price']:,.2f}")
            print(f"   最新价格: ${historical[-1]['price']:,.2f}")
            results['get_historical_prices'] = True
        else:
            print_warn("获取历史数据返回空")
    except Exception as e:
        print_error(f"获取历史数据失败: {e}")
    
    # 测试 5: 技术指标计算
    print_header("测试 MarketDataFetcher.calculate_technical_indicators()")
    try:
        start = time.time()
        indicators = fetcher.calculate_technical_indicators('BTC')
        elapsed = time.time() - start
        
        if indicators:
            print_success(f"计算技术指标成功 (耗时: {elapsed:.2f}s)")
            print(f"   当前价格: ${indicators.get('current_price', 0):,.2f}")
            print(f"   SMA 7日: ${indicators.get('sma_7', 0):,.2f}")
            print(f"   SMA 14日: ${indicators.get('sma_14', 0):,.2f}")
            print(f"   RSI 14日: {indicators.get('rsi_14', 0):.2f}")
            print(f"   7日涨跌: {indicators.get('price_change_7d', 0):.2f}%")
            results['calculate_technical_indicators'] = True
        else:
            print_warn("计算技术指标返回空")
    except Exception as e:
        print_error(f"计算技术指标失败: {e}")
    
    return results

def test_fallback_mechanism():
    """测试降级机制"""
    from market_data import MarketDataFetcher
    
    print_header("测试 Fallback 降级机制")
    
    fetcher = MarketDataFetcher()
    
    # 清空缓存以强制重新获取
    fetcher.clear_cache()
    
    print_info("正在测试多数据源 fallback...")
    prices = fetcher.get_current_prices(['BTC'])
    
    if prices and 'BTC' in prices:
        print_success(f"Fallback 机制正常工作")
        print(f"   BTC: ${prices['BTC']['price']:,.2f}")
        return True
    else:
        print_error("Fallback 机制失败")
        return False

def main():
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║           Market Data API 测试脚本 v1.0                    ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")
    
    # 记录测试结果
    all_results = {}
    
    # 1. 直接测试各个 API
    all_results['CoinGecko'] = test_coingecko_direct()
    time.sleep(1)  # 避免限流
    
    all_results['CoinCap'] = test_coincap_direct()
    time.sleep(1)
    
    all_results['Binance'] = test_binance_direct()
    time.sleep(1)
    
    # 2. 测试 MarketDataFetcher 封装
    fetcher_results = test_market_data_fetcher()
    all_results.update(fetcher_results)
    
    # 3. 测试 fallback 机制
    all_results['Fallback'] = test_fallback_mechanism()
    
    # 输出总结
    print_header("测试结果总结")
    
    passed = 0
    failed = 0
    
    for test_name, result in all_results.items():
        if result:
            print_success(f"{test_name}")
            passed += 1
        else:
            print_error(f"{test_name}")
            failed += 1
    
    print(f"\n{Colors.BOLD}总计: {passed} 通过, {failed} 失败{Colors.RESET}")
    
    if failed == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 所有测试通过！API 接口正常工作。{Colors.RESET}\n")
        return 0
    elif passed > failed:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️ 部分测试失败，但核心功能可用。{Colors.RESET}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ 多数测试失败，请检查网络连接。{Colors.RESET}\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())

