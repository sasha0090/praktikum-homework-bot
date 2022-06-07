class BadHTTPStatus(Exception):
    """Статус не 200"""
    pass


class TokenLack(Exception):
    """Отсутствие токена"""
    pass
