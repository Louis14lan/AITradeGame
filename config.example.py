# Configuration Example

# Server
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False

# Database
DATABASE_PATH = 'trading_bot.db'

# Trading
AUTO_TRADING = True
# 交易频率由数据库 settings 表控制（前端设置弹窗可改），此处已不再使用
COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']

# Market Data (数据源统一为 Gate.io)
MARKET_API_CACHE = 5  # seconds

# Refresh Rates (frontend)
MARKET_REFRESH = 5000  # ms
PORTFOLIO_REFRESH = 10000  # ms
TRADE_FEE_RATE = 0.002  # 交易费率：0.2%（双向收费）

