

class UiConfig:
    def __init__(self, args):
        self.host = args.host
        self.port = args.port

    def __str__(self):
        return ", ".join(f"{key}={value}" for key, value in self.__dict__.items())