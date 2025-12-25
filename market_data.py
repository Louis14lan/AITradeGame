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
    
    def get_kline_data(self, coin: str, interval: str = '1h', limit: int = 100) -> List[Dict]:
        """
        Get K-line/candlestick data from exchanges

        Args:
            coin: Coin symbol (e.g., 'BTC', 'ETH')
            interval: Time interval ('1m', '5m', '15m', '30m', '1h', '4h', '1d', etc.)
            limit: Number of data points to retrieve (default: 100)

        Returns:
            List of dicts with keys: timestamp, open, high, low, close, volume
        """
        cache_key = f'kline_{coin}_{interval}_{limit}'

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Try exchanges in order: OKX -> Gate.io -> Binance
        kline_data = self._get_kline_from_okx(coin, interval, limit)

        if not kline_data:
            kline_data = self._get_kline_from_gateio(coin, interval, limit)

        if not kline_data:
            kline_data = self._get_kline_from_binance(coin, interval, limit)

        if not kline_data:
            # Try stale cache
            stale = self._get_cached(cache_key, allow_stale=True)
            if stale:
                return stale
            return []

        self._set_cache(cache_key, kline_data)
        return kline_data

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
    
    def _get_kline_from_okx(self, coin: str, interval: str, limit: int) -> List[Dict]:
        """
        Get K-line data from OKX
        OKX interval format: '1m', '3m', '5m', '15m', '30m', '1H', '2H', '4H', '6H', '12H', '1D', '1W', '1M'
        """
        try:
            if coin not in self.okx_symbols:
                return []

            # Convert interval to OKX format (OKX uses uppercase H/D/W/M)
            interval_map = {
                '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '1H', '2h': '2H', '4h': '4H', '6h': '6H', '12h': '12H',
                '1d': '1D', '1w': '1W', '1M': '1M'
            }
            okx_interval = interval_map.get(interval.lower(), '1H')

            symbol = self.okx_symbols[coin]
            response = self._request_with_retry(
                'okx',
                f"{self.okx_base_url}/market/candles",
                params={
                    'instId': symbol,
                    'bar': okx_interval,
                    'limit': str(limit)
                },
                timeout=10
            )

            if not response:
                return []

            data = response.json()
            if data.get('code') != '0' or not data.get('data'):
                return []

            kline_data = []
            for candle in data['data']:
                # OKX format: [timestamp, open, high, low, close, volume, volumeCcy, volumeCcyQuote, confirm]
                kline_data.append({
                    'timestamp': int(candle[0]),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })

            # OKX returns newest first, reverse to oldest first
            kline_data.reverse()

            if kline_data:
                print(f"[INFO] Got {len(kline_data)} {interval} klines from OKX for {coin}")
            return kline_data

        except Exception as e:
            print(f"[ERROR] OKX kline data failed for {coin}: {e}")
            return []

    def _get_kline_from_gateio(self, coin: str, interval: str, limit: int) -> List[Dict]:
        """
        Get K-line data from Gate.io
        Gate.io interval format: '10s', '1m', '5m', '15m', '30m', '1h', '4h', '8h', '1d', '7d'
        """
        try:
            if coin not in self.gateio_symbols:
                return []

            # Gate.io uses lowercase intervals
            interval_map = {
                '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '1h', '4h': '4h', '8h': '8h',
                '1d': '1d', '7d': '7d'
            }
            gateio_interval = interval_map.get(interval.lower(), '1h')

            symbol = self.gateio_symbols[coin]
            response = self._request_with_retry(
                'gateio',
                f"{self.gateio_base_url}/spot/candlesticks",
                params={
                    'currency_pair': symbol,
                    'interval': gateio_interval,
                    'limit': limit
                },
                timeout=10
            )

            if not response:
                return []

            data = response.json()
            if not isinstance(data, list):
                return []

            kline_data = []
            for candle in data:
                # Gate.io format: [timestamp, volume, close, high, low, open]
                kline_data.append({
                    'timestamp': int(candle[0]) * 1000,  # Convert to milliseconds
                    'open': float(candle[5]),
                    'high': float(candle[3]),
                    'low': float(candle[4]),
                    'close': float(candle[2]),
                    'volume': float(candle[1])
                })

            if kline_data:
                print(f"[INFO] Got {len(kline_data)} {interval} klines from Gate.io for {coin}")
            return kline_data

        except Exception as e:
            print(f"[ERROR] Gate.io kline data failed for {coin}: {e}")
            return []

    def _get_kline_from_binance(self, coin: str, interval: str, limit: int) -> List[Dict]:
        """
        Get K-line data from Binance
        Binance interval format: '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'
        """
        try:
            if coin not in self.binance_symbols:
                return []

            # Binance uses lowercase intervals
            interval_map = {
                '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
                '1d': '1d', '3d': '3d', '1w': '1w', '1M': '1M'
            }
            binance_interval = interval_map.get(interval.lower(), '1h')

            symbol = self.binance_symbols[coin]
            response = self._request_with_retry(
                'binance',
                f"{self.binance_base_url}/klines",
                params={
                    'symbol': symbol,
                    'interval': binance_interval,
                    'limit': limit
                },
                timeout=10
            )

            if not response:
                return []

            data = response.json()
            if not isinstance(data, list):
                return []

            kline_data = []
            for candle in data:
                # Binance format: [openTime, open, high, low, close, volume, closeTime, ...]
                kline_data.append({
                    'timestamp': int(candle[0]),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })

            if kline_data:
                print(f"[INFO] Got {len(kline_data)} {interval} klines from Binance for {coin}")
            return kline_data

        except Exception as e:
            print(f"[ERROR] Binance kline data failed for {coin}: {e}")
            return []

    def _get_historical_from_coincap(self, coin: str, days: int) -> List[Dict]:
        """Get historical data from CoinCap (volume data limited)"""
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
            historical = []

            for item in data.get('data', []):
                # CoinCap history API doesn't provide volume in history endpoint
                # Use approximate volume based on price
                historical.append({
                    'timestamp': item['time'],
                    'price': float(item['priceUsd']),
                    'volume': 0  # Will be approximated if needed
                })

            return historical

        except Exception as e:
            print(f"[ERROR] CoinCap historical data failed for {coin}: {e}")
            return []
    
    def _get_historical_from_coingecko(self, coin: str, days: int) -> List[Dict]:
        """Get historical data from CoinGecko (with volume)"""
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
            prices_data = data.get('prices', [])
            volumes_data = data.get('total_volumes', [])

            # Combine prices and volumes
            historical = []
            for i, price_item in enumerate(prices_data):
                volume = volumes_data[i][1] if i < len(volumes_data) else 0
                historical.append({
                    'timestamp': price_item[0],
                    'price': price_item[1],
                    'volume': volume
                })

            return historical

        except Exception as e:
            print(f"[ERROR] CoinGecko historical data failed for {coin}: {e}")
            return []
    
    def calculate_technical_indicators(self, coin: str, interval: str = '3m') -> Dict:
        """
        Calculate comprehensive technical indicators for high-frequency trading

        Args:
            coin: Coin symbol (e.g., 'BTC', 'ETH')
            interval: K-line interval, default '3m' for 3-minute trading
                     Options: '1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'

        Returns:
            Dict with 25+ technical indicators
        """
        cache_key = f'technical_{coin}_{interval}'

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Get K-line data (200 candles = ~10 hours for 3m interval)
        # This provides sufficient data for EMA50 (50*3m = 150 minutes)
        kline_data = self.get_kline_data(coin, interval=interval, limit=200)

        if not kline_data or len(kline_data) < 50:
            # Fallback: Try hourly data if K-line unavailable
            print(f"[WARN] Insufficient {interval} K-line data for {coin}, falling back to daily data")
            return self._calculate_indicators_from_daily_data(coin)

        # Extract OHLCV data from K-lines
        prices = [k['close'] for k in kline_data]
        volumes = [k['volume'] for k in kline_data]
        current_price = prices[-1]
        current_volume = volumes[-1] if volumes else 0

        # === 趋势指标 ===
        ema_9 = self._calculate_ema(prices, 9)
        ema_21 = self._calculate_ema(prices, 21)
        ema_50 = self._calculate_ema(prices, 50) if len(prices) >= 50 else ema_21

        # MACD (12, 26, 9)
        macd_line, signal_line, macd_histogram = self._calculate_macd(prices)

        # === 动量指标 ===
        rsi_14 = self._calculate_rsi(prices, 14)
        stoch_rsi = self._calculate_stochastic_rsi(prices, 14)
        roc_10 = self._calculate_roc(prices, 10)  # 10 periods price change rate

        # === 波动率指标 ===
        atr_14 = self._calculate_atr(kline_data, 14)  # Use real OHLC data
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices, 20, 2)

        # === 成交量指标 ===
        volume_ma_5 = self._calculate_volume_ma(volumes, 5)
        volume_ma_20 = self._calculate_volume_ma(volumes, 20)
        volume_ratio = self._calculate_volume_ratio(current_volume, volume_ma_20)
        obv = self._calculate_obv(prices, volumes)
        volume_trend = self._calculate_volume_trend(volumes)
        price_volume_divergence = self._detect_price_volume_divergence(prices, volumes)

        # === 多周期价格变化 ===
        price_changes = self._calculate_price_changes_from_kline(coin, interval)

        # === 趋势强度和方向 ===
        trend_strength = self._calculate_trend_strength(ema_9, ema_21, ema_50, current_price)
        trend_direction = self._determine_trend_direction(ema_9, ema_21, ema_50)

        # === 价格位置分析 ===
        price_position = self._calculate_price_position(current_price, bb_upper, bb_lower)

        # === 波动率水平 ===
        volatility_level = self._calculate_volatility_level(atr_14, current_price)

        result = {
            # 基础价格信息
            'current_price': current_price,

            # 趋势指标
            'ema_9': ema_9,
            'ema_21': ema_21,
            'ema_50': ema_50,
            'macd': macd_line,
            'macd_signal': signal_line,
            'macd_histogram': macd_histogram,

            # 动量指标
            'rsi_14': rsi_14,
            'stoch_rsi': stoch_rsi,
            'roc_10': roc_10,

            # 波动率指标
            'atr_14': atr_14,
            'bb_upper': bb_upper,
            'bb_middle': bb_middle,
            'bb_lower': bb_lower,
            'bb_width': ((bb_upper - bb_lower) / bb_middle * 100) if bb_middle > 0 else 0,

            # 成交量指标
            'volume_24h': current_volume,
            'volume_ma_5': volume_ma_5,
            'volume_ma_20': volume_ma_20,
            'volume_ratio': volume_ratio,
            'obv': obv,
            'volume_trend': volume_trend,  # increasing/decreasing/stable
            'price_volume_divergence': price_volume_divergence,  # bullish/bearish/none

            # 多周期价格变化
            'change_1h': price_changes.get('1h', 0),
            'change_4h': price_changes.get('4h', 0),
            'change_24h': price_changes.get('24h', 0),
            'change_7d': price_changes.get('7d', 0),

            # 综合分析
            'trend_strength': trend_strength,  # -100 to 100
            'trend_direction': trend_direction,  # bullish/bearish/neutral
            'price_position': price_position,  # upper/middle/lower
            'volatility_level': volatility_level,  # high/medium/low
        }

        self._set_cache(cache_key, result)
        return result

    def _calculate_indicators_from_daily_data(self, coin: str) -> Dict:
        """
        Fallback method: Calculate indicators from daily/hourly data when K-line unavailable

        This is used when:
        1. Exchange doesn't provide K-line data for the coin
        2. K-line API fails or returns insufficient data
        3. Small-cap coins with limited data availability
        """
        cache_key = f'technical_{coin}_fallback'

        # Try stale cache first
        stale = self._get_cached(cache_key, allow_stale=True)
        if stale:
            print(f"[INFO] Using stale cache for {coin} indicators")
            return stale

        # Get historical daily/hourly data
        historical = self.get_historical_prices(coin, days=60)

        if not historical or len(historical) < 14:
            # Last resort: return minimal indicators
            current = self.get_current_prices([coin])
            if coin in current:
                return self._get_minimal_indicators(current[coin])
            return {}

        # Extract price and volume data
        prices = [p['price'] for p in historical]
        volumes = [p.get('volume', 0) for p in historical]
        current_price = prices[-1]
        current_volume = volumes[-1] if volumes else 0

        # Calculate all indicators using daily data
        ema_9 = self._calculate_ema(prices, 9)
        ema_21 = self._calculate_ema(prices, 21)
        ema_50 = self._calculate_ema(prices, 50) if len(prices) >= 50 else ema_21

        macd_line, signal_line, macd_histogram = self._calculate_macd(prices)

        rsi_14 = self._calculate_rsi(prices, 14)
        stoch_rsi = self._calculate_stochastic_rsi(prices, 14)
        roc_10 = self._calculate_roc(prices, 10)

        # ATR with approximated OHLC
        atr_14 = self._calculate_atr_approximated(historical, 14)
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices, 20, 2)

        volume_ma_5 = self._calculate_volume_ma(volumes, 5)
        volume_ma_20 = self._calculate_volume_ma(volumes, 20)
        volume_ratio = self._calculate_volume_ratio(current_volume, volume_ma_20)
        obv = self._calculate_obv(prices, volumes)
        volume_trend = self._calculate_volume_trend(volumes)
        price_volume_divergence = self._detect_price_volume_divergence(prices, volumes)

        price_changes = self._calculate_price_changes_fallback(prices, current_price)

        trend_strength = self._calculate_trend_strength(ema_9, ema_21, ema_50, current_price)
        trend_direction = self._determine_trend_direction(ema_9, ema_21, ema_50)
        price_position = self._calculate_price_position(current_price, bb_upper, bb_lower)
        volatility_level = self._calculate_volatility_level(atr_14, current_price)

        result = {
            'current_price': current_price,
            'ema_9': ema_9,
            'ema_21': ema_21,
            'ema_50': ema_50,
            'macd': macd_line,
            'macd_signal': signal_line,
            'macd_histogram': macd_histogram,
            'rsi_14': rsi_14,
            'stoch_rsi': stoch_rsi,
            'roc_10': roc_10,
            'atr_14': atr_14,
            'bb_upper': bb_upper,
            'bb_middle': bb_middle,
            'bb_lower': bb_lower,
            'bb_width': ((bb_upper - bb_lower) / bb_middle * 100) if bb_middle > 0 else 0,
            'volume_24h': current_volume,
            'volume_ma_5': volume_ma_5,
            'volume_ma_20': volume_ma_20,
            'volume_ratio': volume_ratio,
            'obv': obv,
            'volume_trend': volume_trend,
            'price_volume_divergence': price_volume_divergence,
            'change_1h': price_changes.get('1h', 0),
            'change_4h': price_changes.get('4h', 0),
            'change_24h': price_changes.get('24h', 0),
            'change_7d': price_changes.get('7d', 0),
            'trend_strength': trend_strength,
            'trend_direction': trend_direction,
            'price_position': price_position,
            'volatility_level': volatility_level,
        }

        self._set_cache(cache_key, result)
        return result

    def _get_minimal_indicators(self, price_data: Dict) -> Dict:
        """Return minimal indicators when insufficient historical data"""
        price = price_data['price']
        return {
            'current_price': price,
            'ema_9': price,
            'ema_21': price,
            'ema_50': price,
            'macd': 0,
            'macd_signal': 0,
            'macd_histogram': 0,
            'rsi_14': 50,
            'stoch_rsi': 50,
            'roc_10': 0,
            'atr_14': 0,
            'bb_upper': price * 1.02,
            'bb_middle': price,
            'bb_lower': price * 0.98,
            'bb_width': 4,
            'volume_24h': 0,
            'volume_ma_5': 0,
            'volume_ma_20': 0,
            'volume_ratio': 1.0,
            'obv': 0,
            'volume_trend': 'stable',
            'price_volume_divergence': 'none',
            'change_1h': price_data.get('change_1h', 0),
            'change_4h': price_data.get('change_1h', 0),
            'change_24h': price_data.get('change_24h', 0),
            'change_7d': 0,
            'trend_strength': 0,
            'trend_direction': 'neutral',
            'price_position': 'middle',
            'volatility_level': 'medium',
        }

    def _calculate_ema(self, prices: list, period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return prices[-1] if prices else 0

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_macd(self, prices: list, fast=12, slow=26, signal=9) -> tuple:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(prices) < slow:
            return 0, 0, 0

        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)
        macd_line = ema_fast - ema_slow

        # Calculate signal line (EMA of MACD)
        # Simplified: use last 9 values approximation
        signal_line = macd_line * 0.8  # Approximation
        macd_histogram = macd_line - signal_line

        return macd_line, signal_line, macd_histogram

    def _calculate_rsi(self, prices: list, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return 50

        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]

        avg_gain = sum(gains[-period:]) / period if gains else 0
        avg_loss = sum(losses[-period:]) / period if losses else 0

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_stochastic_rsi(self, prices: list, period: int = 14) -> float:
        """Calculate Stochastic RSI for more sensitive momentum signals"""
        if len(prices) < period + 1:
            return 50

        rsi_values = []
        for i in range(period, len(prices)):
            rsi = self._calculate_rsi(prices[:i+1], period)
            rsi_values.append(rsi)

        if len(rsi_values) < period:
            return 50

        recent_rsi = rsi_values[-period:]
        rsi_min = min(recent_rsi)
        rsi_max = max(recent_rsi)

        if rsi_max - rsi_min == 0:
            return 50

        stoch_rsi = ((rsi_values[-1] - rsi_min) / (rsi_max - rsi_min)) * 100
        return stoch_rsi

    def _calculate_roc(self, prices: list, period: int = 10) -> float:
        """Calculate Rate of Change (ROC)"""
        if len(prices) < period + 1:
            return 0

        current_price = prices[-1]
        past_price = prices[-period-1]

        if past_price == 0:
            return 0

        roc = ((current_price - past_price) / past_price) * 100
        return roc

    def _calculate_atr(self, kline_data: list, period: int = 14) -> float:
        """
        Calculate Average True Range (ATR) for volatility measurement using real OHLC data

        Args:
            kline_data: List of K-line candles with 'high', 'low', 'close' keys
            period: ATR period (default: 14)

        Returns:
            ATR value
        """
        if len(kline_data) < period + 1:
            return 0

        true_ranges = []
        for i in range(1, len(kline_data)):
            # Use real OHLC data from K-lines
            high = kline_data[i].get('high', kline_data[i].get('close', 0))
            low = kline_data[i].get('low', kline_data[i].get('close', 0))
            close = kline_data[i].get('close', 0)
            prev_close = kline_data[i-1].get('close', 0)

            # True Range formula: max(H-L, |H-PC|, |L-PC|)
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # Average True Range = SMA of True Ranges
        atr = sum(true_ranges[-period:]) / period if true_ranges else 0
        return atr

    def _calculate_atr_approximated(self, historical: list, period: int = 14) -> float:
        """
        Calculate ATR with approximated OHLC (fallback method for daily data)

        This is used when only daily price data is available without real OHLC.
        Approximates high/low as ±1% of close price.
        """
        if len(historical) < period + 1:
            return 0

        true_ranges = []
        for i in range(1, len(historical)):
            price = historical[i].get('price', 0)
            high = price * 1.01  # Approximate high (+1%)
            low = price * 0.99   # Approximate low (-1%)
            prev_close = historical[i-1].get('price', 0)

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        atr = sum(true_ranges[-period:]) / period if true_ranges else 0
        return atr

    def _calculate_bollinger_bands(self, prices: list, period: int = 20, std_dev: float = 2) -> tuple:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            price = prices[-1]
            return price * 1.02, price, price * 0.98

        recent_prices = prices[-period:]
        middle_band = sum(recent_prices) / period

        # Calculate standard deviation
        variance = sum((p - middle_band) ** 2 for p in recent_prices) / period
        std = variance ** 0.5

        upper_band = middle_band + (std_dev * std)
        lower_band = middle_band - (std_dev * std)

        return upper_band, middle_band, lower_band

    def _calculate_price_changes_from_kline(self, coin: str, base_interval: str = '3m') -> Dict:
        """
        Calculate price changes over multiple timeframes using K-line data

        Args:
            coin: Coin symbol
            base_interval: Base interval used for main indicators (e.g., '3m')

        Returns:
            Dict with keys: '1h', '4h', '24h', '7d' containing percentage changes
        """
        changes = {}

        try:
            # Get 1h K-line data (last 2 candles for 1h change)
            kline_1h = self.get_kline_data(coin, '1h', 2)
            if len(kline_1h) >= 2 and kline_1h[-2]['close'] > 0:
                changes['1h'] = ((kline_1h[-1]['close'] - kline_1h[-2]['close']) / kline_1h[-2]['close'] * 100)
            else:
                changes['1h'] = 0

            # Get 4h K-line data (last 2 candles for 4h change)
            kline_4h = self.get_kline_data(coin, '4h', 2)
            if len(kline_4h) >= 2 and kline_4h[-2]['close'] > 0:
                changes['4h'] = ((kline_4h[-1]['close'] - kline_4h[-2]['close']) / kline_4h[-2]['close'] * 100)
            else:
                changes['4h'] = 0

            # Get 1d K-line data for 24h and 7d changes
            kline_1d = self.get_kline_data(coin, '1d', 8)

            # 24h change (last 2 daily candles)
            if len(kline_1d) >= 2 and kline_1d[-2]['close'] > 0:
                changes['24h'] = ((kline_1d[-1]['close'] - kline_1d[-2]['close']) / kline_1d[-2]['close'] * 100)
            else:
                changes['24h'] = 0

            # 7d change (8 daily candles: current vs 7 days ago)
            if len(kline_1d) >= 8 and kline_1d[-8]['close'] > 0:
                changes['7d'] = ((kline_1d[-1]['close'] - kline_1d[-8]['close']) / kline_1d[-8]['close'] * 100)
            else:
                changes['7d'] = 0

        except Exception as e:
            print(f"[WARN] Failed to calculate price changes from K-line for {coin}: {e}")
            changes = {'1h': 0, '4h': 0, '24h': 0, '7d': 0}

        return changes

    def _calculate_price_changes_fallback(self, prices: list, current: float) -> Dict:
        """Fallback method using daily price data for approximation"""
        changes = {}

        # Approximate hourly data from daily data
        # Note: This is simplified since we only have daily data
        if len(prices) >= 1:
            changes['1h'] = ((current - prices[-1]) / prices[-1] * 100) if prices[-1] > 0 else 0
            changes['4h'] = ((current - prices[-1]) / prices[-1] * 100) if prices[-1] > 0 else 0
        if len(prices) >= 2:
            changes['24h'] = ((current - prices[-2]) / prices[-2] * 100) if prices[-2] > 0 else 0
        if len(prices) >= 8:
            changes['7d'] = ((current - prices[-8]) / prices[-8] * 100) if prices[-8] > 0 else 0

        return changes

    def _calculate_trend_strength(self, ema_9: float, ema_21: float, ema_50: float, current_price: float) -> float:
        """Calculate trend strength (-100 to 100, positive = bullish, negative = bearish)"""
        # Compare EMAs alignment
        if ema_9 > ema_21 > ema_50:
            # Strong bullish trend
            strength = 50 + min(((ema_9 - ema_50) / ema_50 * 100), 50)
        elif ema_9 < ema_21 < ema_50:
            # Strong bearish trend
            strength = -50 - min(((ema_50 - ema_9) / ema_50 * 100), 50)
        else:
            # Mixed or weak trend
            strength = ((ema_9 - ema_50) / ema_50 * 100) if ema_50 > 0 else 0

        return max(-100, min(100, strength))

    def _determine_trend_direction(self, ema_9: float, ema_21: float, ema_50: float) -> str:
        """Determine trend direction based on EMA alignment"""
        if ema_9 > ema_21 > ema_50:
            return 'bullish'
        elif ema_9 < ema_21 < ema_50:
            return 'bearish'
        else:
            return 'neutral'

    def _calculate_price_position(self, current_price: float, bb_upper: float, bb_lower: float) -> str:
        """Calculate price position relative to Bollinger Bands"""
        bb_range = bb_upper - bb_lower
        if bb_range == 0:
            return 'middle'

        position = (current_price - bb_lower) / bb_range

        if position > 0.7:
            return 'upper'
        elif position < 0.3:
            return 'lower'
        else:
            return 'middle'

    def _calculate_volatility_level(self, atr: float, current_price: float) -> str:
        """Calculate volatility level based on ATR"""
        if current_price == 0:
            return 'medium'

        atr_percentage = (atr / current_price) * 100

        if atr_percentage > 3:
            return 'high'
        elif atr_percentage < 1:
            return 'low'
        else:
            return 'medium'

    def _calculate_volume_ma(self, volumes: list, period: int) -> float:
        """Calculate Volume Moving Average"""
        if not volumes or len(volumes) < period:
            return 0

        recent_volumes = volumes[-period:]
        return sum(recent_volumes) / period

    def _calculate_volume_ratio(self, current_volume: float, volume_ma: float) -> float:
        """Calculate volume ratio (current / average)"""
        if volume_ma == 0:
            return 1.0

        return current_volume / volume_ma

    def _calculate_obv(self, prices: list, volumes: list) -> float:
        """Calculate On-Balance Volume (OBV)"""
        if not prices or not volumes or len(prices) < 2:
            return 0

        obv = 0
        for i in range(1, len(prices)):
            if prices[i] > prices[i-1]:
                obv += volumes[i]
            elif prices[i] < prices[i-1]:
                obv -= volumes[i]
            # If price unchanged, OBV unchanged

        return obv

    def _calculate_volume_trend(self, volumes: list, period: int = 5) -> str:
        """Determine volume trend (increasing/decreasing/stable)"""
        if not volumes or len(volumes) < period * 2:
            return 'stable'

        recent_avg = sum(volumes[-period:]) / period
        previous_avg = sum(volumes[-period*2:-period]) / period

        if previous_avg == 0:
            return 'stable'

        change_pct = ((recent_avg - previous_avg) / previous_avg) * 100

        if change_pct > 20:
            return 'increasing'
        elif change_pct < -20:
            return 'decreasing'
        else:
            return 'stable'

    def _detect_price_volume_divergence(self, prices: list, volumes: list, period: int = 10) -> str:
        """Detect price-volume divergence"""
        if not prices or not volumes or len(prices) < period + 1:
            return 'none'

        # Get recent data
        recent_prices = prices[-period:]
        recent_volumes = volumes[-period:]

        # Calculate price trend
        price_start = recent_prices[0]
        price_end = recent_prices[-1]
        price_trend = 'up' if price_end > price_start else 'down' if price_end < price_start else 'flat'

        # Calculate volume trend
        volume_first_half = sum(recent_volumes[:period//2]) / (period//2)
        volume_second_half = sum(recent_volumes[period//2:]) / (period - period//2)

        volume_increasing = volume_second_half > volume_first_half * 1.1

        # Detect divergence
        if price_trend == 'up' and not volume_increasing:
            # Price up but volume down = bearish divergence
            return 'bearish'
        elif price_trend == 'down' and volume_increasing:
            # Price down but volume up = bullish divergence (capitulation)
            return 'bullish'
        else:
            return 'none'

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
