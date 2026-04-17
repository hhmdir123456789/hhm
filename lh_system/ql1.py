class MyStrategy(BaseStrategy):
    def __init__(self, data):
        super().__init__(data)
        self.short_window = 5
        self.long_window = 20
        self.threshold = 1.2
        self.sell_threshold = 0.003

    def next(self):
        short_ma = self.data['close'].rolling(window=self.short_window).mean()
        long_ma = self.data['close'].rolling(window=self.long_window).mean()

        if short_ma.iloc[-1] > long_ma.iloc[-1] and short_ma.iloc[-2] <= long_ma.iloc[-2]:
            if self.data['volume'].iloc[-1] > self.data['volume'].iloc[-2] * self.threshold:
                self.buy()

        if self.position:
            if self.data['close'].iloc[-1] < self.data['close'].iloc[-2] * (1 - self.sell_threshold):
                self.sell()