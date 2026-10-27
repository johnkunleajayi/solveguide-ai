class VisionError(Exception):
    """Only safe public fields; never wrap or stringify provider exceptions."""

    def __init__(self, code: str, message: str, status: int = 502):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(code)
