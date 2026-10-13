class ProxyError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.message = message
        self.status = status


class DNError(Exception):
    pass
