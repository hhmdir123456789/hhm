class Strategy():
    def __init__(self):
        self.short_window = 5
        self.long_window = 20
        self.entry_threshold = 1.2
        self.stop_loss = 0.003

    def next(self):
        short_ma = self.data['close'].rolling(window=self.short_window).mean()
        long_ma = self.data['close'].rolling(window=self.long_window).mean()
        volume = self.data['volume']

        if short_ma.iloc[-1] > long_ma.iloc[-1] and short_ma.iloc[-2] <= long_ma.iloc[-2]:
            if volume.iloc[-1] > volume.iloc[-2] * self.entry_threshold:
                self.buy()

        if self.position:
            if self.data['close'].iloc[-1] <= self.data['close'].iloc[-2] * (1 - self.stop_loss):
                self.sell()