# The investment universe consists of all U.S. firms listed on the NYSE, AMEX, and NASDAQ with share codes 10 and 11 with positive equity book value
# in Compustat for the previous year. Excluded are stocks with an end-of-month price below $5, stocks that are not traded during the month, stocks tha
# do not record return observations for the previous 12 months and stocks for which there are no available records to construct firm characteristics 
# known to predict the cross-section of average returns. Firstly, construct the MAD as MA(21) divided by the MA(200), where MA(21) is the stock price
# moving average based on 21 trading days (approximately the past one month) and MA(200) is the corresponding 200-day moving average. Using a treshold 
# set a fixed value of 0.2, long the stocks with MAD equal or higher than 1.2 and short stocks with MAD equal or lower than 0.8. Stocks are equally-weighted 
# and the strategy is rebalanced monthly.

import numpy as np

class MovingAveragesDistance(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2000, 1, 1)
        self.SetCash(100000)

        self.coarse_count = 500
        
        self.period = 200
        
        self.data = {}
        
        self.long = []
        self.short = []
        
        self.symbol = self.AddEquity('SPY', Resolution.Daily).Symbol
        
        self.selection_flag = False
        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.CoarseSelectionFunction, self.FineSelectionFunction)
        self.Schedule.On(self.DateRules.MonthStart(self.symbol), self.TimeRules.AfterMarketOpen(self.symbol), self.Selection)
    
    def OnSecuritiesChanged(self, changes):
        for security in changes.AddedSecurities:
            security.SetFeeModel(CustomFeeModel(self))
            security.SetLeverage(5)

    def CoarseSelectionFunction(self, coarse):
        # Update the rolling window every day.
        for stock in coarse:
            symbol = stock.Symbol

            # Store monthly price.
            if symbol in self.data:
                self.data[symbol].update(stock.AdjustedPrice)

        if not self.selection_flag:
            return Universe.Unchanged

        # selected = [x.Symbol for x in coarse if x.HasFundamentalData and x.Market == 'usa' and x.Price > 5]
        sorted_by_dollar_volume = sorted([x for x in coarse if x.HasFundamentalData and x.Market == 'usa' and x.Price > 5],
            key=lambda x: x.DollarVolume, reverse=True)
            
        selected = [x.Symbol for x in sorted_by_dollar_volume]

        # Warmup price rolling windows.
        for symbol in selected:
            if symbol in self.data:
                continue

            self.data[symbol] = SymbolData(symbol, self.period)
            history = self.History(symbol, self.period, Resolution.Daily)
            if history.empty:
                self.Log(f"Not enough data for {symbol} yet")
                continue
            closes = history.loc[symbol].close
            for time, close in closes.iteritems():
                self.data[symbol].update(close)

        return [x for x in selected if self.data[x].is_ready()][:self.coarse_count]
        
    def FineSelectionFunction(self, fine):
        fine = [x for x in fine if ((x.SecurityReference.ExchangeId == "NYS") or (x.SecurityReference.ExchangeId == "NAS") or (x.SecurityReference.ExchangeId == "ASE"))]
        
        MAD = {}
        for stock in fine:
            symbol = stock.Symbol
            
            prices = self.data[symbol].return_prices()
            ma21 = np.average(prices[:21])
            ma200 = np.average(prices)
            
            MAD[symbol] = ma21 / ma200
    
        self.long = [x[0] for x in MAD.items() if x[1] >= 1.2]
        self.short = [x[0] for x in MAD.items() if x[1] <= 0.8]
        
        return self.long + self.short

    def OnData(self, data):
        if not self.selection_flag:
            return
        self.selection_flag = False
        
        self.Liquidate()
        
        count_long = len(self.long)
        count_short = len(self.short)
        
        for symbol in self.long:
            if self.Securities[symbol].Price != 0 and self.Securities[symbol].IsTradable:
                self.SetHoldings(symbol, 1/count_long)
                
        for symbol in self.short:
            if self.Securities[symbol].Price != 0 and self.Securities[symbol].IsTradable:
                self.SetHoldings(symbol, -1/count_short)

        self.long.clear()
        self.short.clear()
    
    def Selection(self):
        self.selection_flag = True
    
class SymbolData():
    def __init__(self, symbol, period):
        self.Symbol = symbol
        self.Prices = RollingWindow[float](period)
        
    def update(self, price):
        self.Prices.Add(price)
        
    def is_ready(self):
        return self.Prices.IsReady
        
    def return_prices(self):
        return [x for x in self.Prices]
        
class CustomFeeModel(FeeModel):
    def GetOrderFee(self, parameters):
        fee = parameters.Security.Price * parameters.Order.AbsoluteQuantity * 0.00005
        return OrderFee(CashAmount(fee, "USD"))
