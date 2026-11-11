"""Tracked universe. Edit freely: tickers are Yahoo Finance symbols."""

NIFTY50 = {
    "RELIANCE": "Reliance Industries", "TCS": "TCS", "HDFCBANK": "HDFC Bank", "ICICIBANK": "ICICI Bank",
    "INFY": "Infosys", "BHARTIARTL": "Bharti Airtel", "ITC": "ITC", "SBIN": "State Bank of India",
    "LT": "Larsen & Toubro", "HINDUNILVR": "Hindustan Unilever", "KOTAKBANK": "Kotak Mahindra Bank",
    "AXISBANK": "Axis Bank", "BAJFINANCE": "Bajaj Finance", "MARUTI": "Maruti Suzuki",
    "SUNPHARMA": "Sun Pharma", "TITAN": "Titan", "ASIANPAINT": "Asian Paints", "NTPC": "NTPC",
    "ULTRACEMCO": "UltraTech Cement", "ONGC": "ONGC", "POWERGRID": "Power Grid", "M&M": "Mahindra & Mahindra",
    "TMPV": "Tata Motors (Passenger Veh.)", "TATASTEEL": "Tata Steel", "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports", "WIPRO": "Wipro", "HCLTECH": "HCL Tech", "TECHM": "Tech Mahindra",
    "JSWSTEEL": "JSW Steel", "COALINDIA": "Coal India", "BAJAJFINSV": "Bajaj Finserv",
    "NESTLEIND": "Nestle India", "DRREDDY": "Dr Reddy's", "CIPLA": "Cipla", "GRASIM": "Grasim",
    "EICHERMOT": "Eicher Motors", "HEROMOTOCO": "Hero MotoCorp", "BRITANNIA": "Britannia",
    "APOLLOHOSP": "Apollo Hospitals", "INDUSINDBK": "IndusInd Bank", "BPCL": "BPCL",
    "HINDALCO": "Hindalco", "DIVISLAB": "Divi's Labs", "TATACONSUM": "Tata Consumer",
    "SBILIFE": "SBI Life", "HDFCLIFE": "HDFC Life", "BAJAJ-AUTO": "Bajaj Auto", "SHRIRAMFIN": "Shriram Finance",
}

MIDCAPS = {
    "PERSISTENT": "Persistent Systems", "COFORGE": "Coforge", "MPHASIS": "Mphasis", "TRENT": "Trent",
    "POLYCAB": "Polycab", "DIXON": "Dixon Technologies", "BHARATFORG": "Bharat Forge", "CUMMINSIND": "Cummins India",
    "PIIND": "PI Industries", "ASTRAL": "Astral", "AUROPHARMA": "Aurobindo Pharma", "LUPIN": "Lupin",
    "ALKEM": "Alkem Labs", "MAXHEALTH": "Max Healthcare", "FORTIS": "Fortis Healthcare", "INDHOTEL": "Indian Hotels",
    "JUBLFOOD": "Jubilant FoodWorks", "VOLTAS": "Voltas", "HAVELLS": "Havells", "PAGEIND": "Page Industries",
    "FEDERALBNK": "Federal Bank", "IDFCFIRSTB": "IDFC First Bank", "AUBANK": "AU Small Finance Bank", "PFC": "Power Finance Corp",
    "RECLTD": "REC Ltd", "BEL": "Bharat Electronics", "HAL": "Hindustan Aeronautics", "BHEL": "BHEL",
    "SAIL": "SAIL", "NMDC": "NMDC", "GODREJPROP": "Godrej Properties", "OBEROIRLTY": "Oberoi Realty",
    "LODHA": "Macrotech Developers", "TVSMOTOR": "TVS Motor", "ASHOKLEY": "Ashok Leyland", "ZYDUSLIFE": "Zydus Lifesciences",
    "MUTHOOTFIN": "Muthoot Finance", "CHOLAFIN": "Cholamandalam Investment", "ABCAPITAL": "Aditya Birla Capital", "IRCTC": "IRCTC",
}

INDICES = {
    # India
    "^NSEI": ("Nifty 50", "India"), "^BSESN": ("Sensex", "India"), "^NSEBANK": ("Bank Nifty", "India"),
    "^CNXIT": ("Nifty IT", "India"),
    # Global
    "^GSPC": ("S&P 500", "US"), "^IXIC": ("NASDAQ", "US"), "^DJI": ("Dow Jones", "US"),
    "^FTSE": ("FTSE 100", "UK"), "^N225": ("Nikkei 225", "Japan"), "000001.SS": ("Shanghai Composite", "China"),
    "^HSI": ("Hang Seng", "China/HK"), "^GDAXI": ("DAX", "Germany"), "^KS11": ("KOSPI", "S. Korea"),
}

COMMODITIES = {
    "GC=F": "Gold", "SI=F": "Silver", "HG=F": "Copper", "PL=F": "Platinum", "PA=F": "Palladium",
    "CL=F": "Crude Oil (WTI)", "BZ=F": "Brent Crude", "NG=F": "Natural Gas",
}

# Rare earths have no liquid free price feed; these ETFs/stocks are the usual proxies.
RARE_EARTH_PROXIES = {"REMX": "VanEck Rare Earth & Strategic Metals ETF", "MP": "MP Materials"}

# Currencies expressed in INR (how many INR for one unit) + the dollar index.
CURRENCIES = {
    "USDINR=X": "US Dollar", "EURINR=X": "Euro", "GBPINR=X": "British Pound",
    "JPYINR=X": "Japanese Yen", "CNYINR=X": "Chinese Yuan", "AEDINR=X": "UAE Dirham",
    "DX-Y.NYB": "US Dollar Index (DXY)",
}

# Rates / bonds (yields, not prices): higher yield = lower bond prices.
YIELDS = {"^TNX": "US 10Y Treasury yield", "^IRX": "US 13-week T-bill yield"}

# Search terms resolved against mfapi.in at run time (Direct plan, Growth). Edit to taste.
MUTUAL_FUNDS = [
    "Parag Parikh Flexi Cap Fund Direct Growth", "HDFC Flexi Cap Fund Direct Growth",
    "Nippon India Small Cap Fund Direct Growth", "SBI Small Cap Fund Direct Growth",
    "Quant Small Cap Fund Direct Growth", "Mirae Asset Large Cap Fund Direct Growth",
    "ICICI Prudential Bluechip Fund Direct Growth", "Axis Bluechip Fund Direct Growth",
    "Kotak Emerging Equity Fund Direct Growth", "Motilal Oswal Midcap Fund Direct Growth",
    "HDFC Mid-Cap Opportunities Fund Direct Growth", "UTI Nifty 50 Index Fund Direct Growth",
    "Nippon India Gold Savings Fund Direct Growth", "SBI Gold Fund Direct Growth",
    "ICICI Prudential Equity & Debt Fund Direct Growth", "HDFC Short Term Debt Fund Direct Growth",
    "Axis Liquid Fund Direct Growth", "Nippon India Silver ETF FoF Direct Growth",
]
