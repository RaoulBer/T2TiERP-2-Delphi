class VerificationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise VerificationError(str(code))
