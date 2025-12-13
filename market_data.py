"""
Market data module - Multi-source API integration with fallback
Supports: OKX, Gate.io, Binance, CoinGecko, CoinCap with rate limiting and caching
(OKX and Gate.io are prioritized for China mainland users)
"""
import requests
import time
import threading
from typing import Dict, List, Optional


class RateLimiter:
    """Global rate limiter for API requests"""
    
    def __init__(self):
        self._last_request_time: Dict[str, float] = {}
        self._min_intervals: Dict[str, float] = {
            'binance': 0.5,      # 500ms between requests
            'coingecko': 10,     # 10s between requests (strict limit)
            'coincap': 1.0,      # 1s between requests
            'okx': 0.5,          # 500ms between requests
            'gateio': 0.5,       # 500ms between requests
        }
        self._lock = threading.Lock()
    
    def wait_if_needed(self, api_name: str):
        """Wait if necessary to respect rate limits"""
        with self._lock:
            min_interval = self._min_intervals.get(api_name, 1.0)
            last_time = self._last_request_time.get(api_name, 0)
            elapsed = time.time() - last_time
            
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                time.sleep(sleep_time)
            
            self._last_request_time[api_name] = time.time()


class MarketDataFetcher:
    """Fetch real-time market data from multiple APIs with fallback"""
    
    def __init__(self):
        # API endpoints
        self.binance_base_url = "https://api.binance.com/api/v3"
        self.coingecko_base_url = "https://api.coingecko.com/api/v3"
        self.coincap_base_url = "https://api.coincap.io/v2"
        self.okx_base_url = "https://www.okx.com/api/v5"
        self.gateio_base_url = "https://api.gateio.ws/api/v4"
        
        # Binance symbol mapping
        self.binance_symbols = {
            'BTC': 'BTCUSDT',
            'ETH': 'ETHUSDT',
            'SOL': 'SOLUSDT',
            'BNB': 'BNBUSDT',
            'XRP': 'XRPUSDT',
            'DOGE': 'DOGEUSDT'
        }
        
        # CoinGecko mapping
        self.coingecko_mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'SOL': 'solana',
            'BNB': 'binancecoin',
            'XRP': 'ripple',
            'DOGE': 'dogecoin'
        }
        
        # CoinCap mapping (uses lowercase ids)
        self.coincap_mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'SOL': 'solana',
            'BNB': 'binance-coin',
            'XRP': 'xrp',
            'DOGE': 'dogecoin'
        }
        
        # OKX symbol mapping
        self.okx_symbols = {
            'BTC': 'BTC-USDT',
            'ETH': 'ETH-USDT',
            'SOL': 'SOL-USDT',
            'BNB': 'BNB-USDT',
            'XRP': 'XRP-USDT',
            'DOGE': 'DOGE-USDT'
        }
        
        # Gate.io symbol mapping
        self.gateio_symbols = {
            'BTC': 'BTC_USDT',
            'ETH': 'ETH_USDT',
            'SOL': 'SOL_USDT',
            'BNB': 'BNB_USDT',
            'XRP': 'XRP_USDT',
            'DOGE': 'DOGE_USDT'
        }
        
        # Cache settings - extended duration
        self._cache: Dict[str, any] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_duration = 30  # Normal cache: 30 seconds
        self._stale_cache_duration = 300  # Stale cache: 5 minutes (fallback)
        
        # Rate limiter
        self._rate_limiter = RateLimiter()
        
        # Retry settings
        self._max_retries = 3
        self._base_retry_delay = 1.0  # Base delay for exponential backoff
        
        # Simulated data for ultimate fallback
        self._simulated_prices = {
            'BTC': {'price': 97000.0, 'change_24h': 1.5},
            'ETH': {'price': 3600.0, 'change_24h': 2.1},
            'SOL': {'price': 220.0, 'change_24h': 3.2},
            'BNB': {'price': 680.0, 'change_24h': 0.8},
            'XRP': {'price': 2.3, 'change_24h': -1.2},
            'DOGE': {'price': 0.40, 'change_24h': 4.5}
        }
    
    def _get_cached(self, cache_key: str, allow_stale: bool = False) -> Optional[any]:
        """Get cached data, optionally allowing stale cache"""
        if cache_key not in self._cache:
            return None
        
        age = time.time() - self._cache_time.get(cache_key, 0)
        
        # Fresh cache
        if age < self._cache_duration:
            return self._cache[cache_key]
        
        # Stale cache (only if allowed)
        if allow_stale and age < self._stale_cache_duration:
            print(f"[WARN] Using stale cache for {cache_key} (age: {age:.1f}s)")
            return self._cache[cache_key]
        
        return None
    
    def _set_cache(self, cache_key: str, data: any):
        """Set cache data"""
        self._cache[cache_key] = data
        self._cache_time[cache_key] = time.time()
    
    def _request_with_retry(self, api_name: str, url: str, params: dict = None, 
                            timeout: int = 10) -> Optional[requests.Response]:
        """Make HTTP request with rate limiting and exponential backoff retry"""
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                # Rate limiting
                self._rate_limiter.wait_if_needed(api_name)

                print(f"[INFO] Requesting {url} with params {params}")
                
                response = requests.get(url, params=params, timeout=timeout)
                
                # Handle rate limit (429) with exponential backoff
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 
                                      self._base_retry_delay * (2 ** attempt)))
                    print(f"[WARN] {api_name} rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2 ** attempt)
                    print(f"[WARN] {api_name} request failed (attempt {attempt + 1}), "
                          f"retrying in {delay}s: {e}")
                    time.sleep(delay)
        
        print(f"[ERROR] {api_name} request failed after {self._max_retries} attempts: {last_error}")
        return None
    
    def get_current_prices(self, coins: List[str]) -> Dict[str, Dict]:
        """Get current prices with multi-source fallback"""
        cache_key = 'prices_' + '_'.join(sorted(coins))
        
        # Check fresh cache first
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        # Try APIs in order: OKX -> Gate.io -> Binance -> CoinGecko -> CoinCap
        # (OKX and Gate.io are China-friendly, prioritized for mainland users)
        prices = self._get_prices_from_okx(coins)
        
        if not prices or len(prices) < len(coins):
            gateio_prices = self._get_prices_from_gateio(coins)
            if gateio_prices:
                prices = gateio_prices
        
        if not prices or len(prices) < len(coins):
            binance_prices = self._get_prices_from_binance(coins)
            if binance_prices:
                prices = binance_prices
        
        if not prices or len(prices) < len(coins):
            coingecko_prices = self._get_prices_from_coingecko(coins)
            if coingecko_prices:
                prices = coingecko_prices
        
        if not prices or len(prices) < len(coins):
            coincap_prices = self._get_prices_from_coincap(coins)
            if coincap_prices:
                prices = coincap_prices
        
        # If all APIs failed, try stale cache
        if not prices:
            stale = self._get_cached(cache_key, allow_stale=True)
            if stale:
                return stale
            
            # Ultimate fallback: simulated data
            print("[WARN] All APIs failed, using simulated prices")
            prices = {coin: self._simulated_prices.get(coin, {'price': 0, 'change_24h': 0}) 
                     for coin in coins}
        
        # Update cache
        self._set_cache(cache_key, prices)
        return prices
    
    def _get_prices_from_coincap(self, coins: List[str]) -> Dict[str, Dict]:
        """Fetch prices from CoinCap API (no geo-restrictions)"""
        try:
            coin_ids = [self.coincap_mapping.get(coin) for coin in coins 
                       if coin in self.coincap_mapping]
            
            if not coin_ids:
                return {}
            
            # CoinCap supports batch query
            ids_param = ','.join(coin_ids)
            response = self._request_with_retry(
                'coincap',
                f"{self.coincap_base_url}/assets",
                params={'ids': ids_param},
                timeout=10
            )
            
            if not response:
                return {}
            
            data = response.json()
            prices = {}
            
            for asset in data.get('data', []):
                asset_id = asset['id']
                # Find corresponding coin symbol
                for coin, coincap_id in self.coincap_mapping.items():
                    if coincap_id == asset_id:
                        prices[coin] = {
                            'price': float(asset['priceUsd']),
                            'change_24h': float(asset.get('changePercent24Hr', 0) or 0)
                        }
                        break
            
            if prices:
                print(f"[INFO] Got prices from CoinCap: {list(prices.keys())}")
            return prices
            
        except Exception as e:
            print(f"[ERROR] CoinCap API failed: {e}")
            return {}
    
    def _get_prices_from_binance(self, coins: List[str]) -> Dict[str, Dict]:
        """Fetch prices from Binance API"""
        try:
            symbols = [self.binance_symbols.get(coin) for coin in coins 
                      if coin in self.binance_symbols]
            
            if not symbols:
                return {}
            
            symbols_param = '[' + ','.join([f'"{s}"' for s in symbols]) + ']'
            
            response = self._request_with_retry(
                'binance',
                f"{self.binance_base_url}/ticker/24hr",
                params={'symbols': symbols_param},
                timeout=5
            )
            
            if not response:
                return {}
            
            data = response.json()
            prices = {}
            
            for item in data:
                symbol = item['symbol']
                for coin, binance_symbol in self.binance_symbols.items():
                    if binance_symbol == symbol:
                        prices[coin] = {
                            'price': float(item['lastPrice']),
                            'change_24h': float(item['priceChangePercent'])
                        }
                        break
            
            if prices:
                print(f"[INFO] Got prices from Binance: {list(prices.keys())}")
            return prices
            
        except Exception as e:
            print(f"[ERROR] Binance API failed: {e}")
            return {}
    
    def _get_prices_from_okx(self, coins: List[str]) -> Dict[str, Dict]:
        """Fetch prices from OKX API (China-friendly)"""
        try:
            prices = {}
            
            for coin in coins:
                if coin not in self.okx_symbols:
                    continue
                
                symbol = self.okx_symbols[coin]
                response = self._request_with_retry(
                    'okx',
                    f"{self.okx_base_url}/market/ticker",
                    params={'instId': symbol},
                    timeout=10
                )
                
                if not response:
                    continue
                
                data = response.json()
                if data.get('code') == '0' and data.get('data'):
                    ticker = data['data'][0]
                    last_price = float(ticker['last'])
                    open_24h = float(ticker.get('open24h', 0) or ticker.get('sodUtc8', 0) or last_price)
                    
                    if open_24h > 0:
                        change_24h = ((last_price - open_24h) / open_24h) * 100
                    else:
                        change_24h = 0
                    
                    prices[coin] = {
                        'price': last_price,
                        'change_24h': change_24h
                    }
            
            if prices:
                print(f"[INFO] Got prices from OKX: {list(prices.keys())}")
            return prices
            
        except Exception as e:
            print(f"[ERROR] OKX API failed: {e}")
            return {}
    
    def _get_prices_from_gateio(self, coins: List[str]) -> Dict[str, Dict]:
        """Fetch prices from Gate.io API (China-friendly)"""
        try:
            # Gate.io supports batch query
            currency_pairs = [self.gateio_symbols[coin] for coin in coins 
                            if coin in self.gateio_symbols]
            
            if not currency_pairs:
                return {}
            
            response = self._request_with_retry(
                'gateio',
                f"{self.gateio_base_url}/spot/tickers",
                timeout=10
            )
            
            if not response:
                return {}
            
            data = response.json()
            prices = {}
            
            # Create a reverse mapping for lookup
            symbol_to_coin = {v: k for k, v in self.gateio_symbols.items()}
            
            for ticker in data:
                currency_pair = ticker.get('currency_pair')
                if currency_pair in symbol_to_coin:
                    coin = symbol_to_coin[currency_pair]
                    prices[coin] = {
                        'price': float(ticker['last']),
                        'change_24h': float(ticker.get('change_percentage', 0) or 0)
                    }
            
            if prices:
                print(f"[INFO] Got prices from Gate.io: {list(prices.keys())}")
            return prices
            
        except Exception as e:
            print(f"[ERROR] Gate.io API failed: {e}")
            return {}
    
    def _get_prices_from_coingecko(self, coins: List[str]) -> Dict[str, Dict]:
        """Fetch prices from CoinGecko API"""
        try:
            coin_ids = [self.coingecko_mapping.get(coin, coin.lower()) for coin in coins]
            
            response = self._request_with_retry(
                'coingecko',
                f"{self.coingecko_base_url}/simple/price",
                params={
                    'ids': ','.join(coin_ids),
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true'
                },
                timeout=10
            )
            
            if not response:
                return {}
            
            data = response.json()
            prices = {}
            
            for coin in coins:
                coin_id = self.coingecko_mapping.get(coin, coin.lower())
                if coin_id in data:
                    prices[coin] = {
                        'price': data[coin_id]['usd'],
                        'change_24h': data[coin_id].get('usd_24h_change', 0)
                    }
            
            if prices:
                print(f"[INFO] Got prices from CoinGecko: {list(prices.keys())} {prices}")
            return prices
            
        except Exception as e:
            print(f"[ERROR] CoinGecko API failed: {e}")
            return {}
    
    def get_market_data(self, coin: str) -> Dict:
        """Get detailed market data with caching"""
        cache_key = f'market_data_{coin}'
        
        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        # Try CoinGecko first (most reliable), then CoinCap as fallback
        data = self._get_market_data_from_coingecko(coin)
        
        if not data:
            data = self._get_market_data_from_coincap(coin)
        
        if not data:
            # Try stale cache
            stale = self._get_cached(cache_key, allow_stale=True)
            if stale:
                return stale
            return {}
        
        self._set_cache(cache_key, data)
        return data
    
    def _get_market_data_from_coincap(self, coin: str) -> Dict:
        """Get market data from CoinCap"""
        try:
            coin_id = self.coincap_mapping.get(coin)
            if not coin_id:
                return {}
            
            response = self._request_with_retry(
                'coincap',
                f"{self.coincap_base_url}/assets/{coin_id}",
                timeout=10
            )
            
            if not response:
                return {}
            
            asset = response.json().get('data', {})
            
            return {
                'current_price': float(asset.get('priceUsd', 0) or 0),
                'market_cap': float(asset.get('marketCapUsd', 0) or 0),
                'total_volume': float(asset.get('volumeUsd24Hr', 0) or 0),
                'price_change_24h': float(asset.get('changePercent24Hr', 0) or 0),
                'price_change_7d': 0,  # CoinCap doesn't provide 7d change directly
                'high_24h': 0,
                'low_24h': 0,
            }
        except Exception as e:
            print(f"[ERROR] CoinCap market data failed for {coin}: {e}")
            return {}
    
    def _get_market_data_from_coingecko(self, coin: str) -> Dict:
        """Get market data from CoinGecko"""
        coin_id = self.coingecko_mapping.get(coin, coin.lower())
        
        try:
            response = self._request_with_retry(
                'coingecko',
                f"{self.coingecko_base_url}/coins/{coin_id}",
                params={'localization': 'false', 'tickers': 'false', 'community_data': 'false'},
                timeout=10
            )
            
            if not response:
                return {}
            
            data = response.json()
            market_data = data.get('market_data', {})
            
            return {
                'current_price': market_data.get('current_price', {}).get('usd', 0),
                'market_cap': market_data.get('market_cap', {}).get('usd', 0),
                'total_volume': market_data.get('total_volume', {}).get('usd', 0),
                'price_change_24h': market_data.get('price_change_percentage_24h', 0),
                'price_change_7d': market_data.get('price_change_percentage_7d', 0),
                'high_24h': market_data.get('high_24h', {}).get('usd', 0),
                'low_24h': market_data.get('low_24h', {}).get('usd', 0),
            }
        except Exception as e:
            print(f"[ERROR] CoinGecko market data failed for {coin}: {e}")
            return {}
    
    def get_historical_prices(self, coin: str, days: int = 7) -> List[Dict]:
        """Get historical prices with caching"""
        cache_key = f'historical_{coin}_{days}'
        
        # Check cache (use longer cache for historical data)
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        # Try CoinGecko first (most reliable), then CoinCap as fallback
        prices = self._get_historical_from_coingecko(coin, days)
        
        if not prices:
            prices = self._get_historical_from_coincap(coin, days)
        
        if not prices:
            # Try stale cache
            stale = self._get_cached(cache_key, allow_stale=True)
            if stale:
                return stale
            return []
        
        self._set_cache(cache_key, prices)
        return prices
    
    def _get_historical_from_coincap(self, coin: str, days: int) -> List[Dict]:
        """Get historical data from CoinCap"""
        try:
            coin_id = self.coincap_mapping.get(coin)
            if not coin_id:
                return []
            
            # CoinCap uses millisecond timestamps
            end_time = int(time.time() * 1000)
            start_time = end_time - (days * 24 * 60 * 60 * 1000)
            
            # Determine interval based on days
            if days <= 1:
                interval = 'm5'  # 5 minute intervals
            elif days <= 7:
                interval = 'h1'  # hourly
            else:
                interval = 'h12'  # 12 hour intervals
            
            response = self._request_with_retry(
                'coincap',
                f"{self.coincap_base_url}/assets/{coin_id}/history",
                params={
                    'interval': interval,
                    'start': start_time,
                    'end': end_time
                },
                timeout=10
            )
            
            if not response:
                return []
            
            data = response.json()
            prices = []
            
            for item in data.get('data', []):
                prices.append({
                    'timestamp': item['time'],
                    'price': float(item['priceUsd'])
                })
            
            return prices
            
        except Exception as e:
            print(f"[ERROR] CoinCap historical data failed for {coin}: {e}")
            return []
    
    def _get_historical_from_coingecko(self, coin: str, days: int) -> List[Dict]:
        """Get historical data from CoinGecko"""
        coin_id = self.coingecko_mapping.get(coin, coin.lower())
        
        try:
            response = self._request_with_retry(
                'coingecko',
                f"{self.coingecko_base_url}/coins/{coin_id}/market_chart",
                params={'vs_currency': 'usd', 'days': days},
                timeout=10
            )
            
            if not response:
                return []
            
            data = response.json()
            prices = []
            
            for price_data in data.get('prices', []):
                prices.append({
                    'timestamp': price_data[0],
                    'price': price_data[1]
                })
            
            return prices
            
        except Exception as e:
            print(f"[ERROR] CoinGecko historical data failed for {coin}: {e}")
            return []
    
    def calculate_technical_indicators(self, coin: str) -> Dict:
        """Calculate technical indicators with better error handling"""
        cache_key = f'technical_{coin}'
        
        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        historical = self.get_historical_prices(coin, days=14)
        
        if not historical or len(historical) < 14:
            # Try stale cache
            stale = self._get_cached(cache_key, allow_stale=True)
            if stale:
                return stale
            
            # Return empty with current price if available
            current = self.get_current_prices([coin])
            if coin in current:
                return {
                    'current_price': current[coin]['price'],
                    'sma_7': current[coin]['price'],
                    'sma_14': current[coin]['price'],
                    'rsi_14': 50,  # Neutral RSI
                    'price_change_7d': current[coin].get('change_24h', 0)
                }
            return {}
        
        prices = [p['price'] for p in historical]
        
        # Simple Moving Average
        sma_7 = sum(prices[-7:]) / 7 if len(prices) >= 7 else prices[-1]
        sma_14 = sum(prices[-14:]) / 14 if len(prices) >= 14 else prices[-1]
        
        # RSI calculation
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]
        
        avg_gain = sum(gains[-14:]) / 14 if gains else 0
        avg_loss = sum(losses[-14:]) / 14 if losses else 0
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        result = {
            'sma_7': sma_7,
            'sma_14': sma_14,
            'rsi_14': rsi,
            'current_price': prices[-1],
            'price_change_7d': ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] > 0 else 0
        }

        self._set_cache(cache_key, result)
        return result
    
    def update_simulated_prices(self, new_prices: Dict[str, Dict]):
        """Update simulated prices (for testing/development)"""
        self._simulated_prices.update(new_prices)
    
    def clear_cache(self):
        """Clear all cached data"""
        self._cache.clear()
        self._cache_time.clear()
        print("[INFO] Cache cleared")
    
    def get_cache_status(self) -> Dict:
        """Get cache status for debugging"""
        now = time.time()
        status = {}
        for key, timestamp in self._cache_time.items():
            age = now - timestamp
            status[key] = {
                'age_seconds': round(age, 1),
                'fresh': age < self._cache_duration,
                'stale_usable': age < self._stale_cache_duration
            }
        return status
