"""
Various exceptions that can be raised by qitensor functions.
"""

__all__ = [
    'BraKetMixtureError',
    'DuplicatedSpaceError',
    'HilbertError',
    'HilbertIndexError',
    'HilbertShapeError',
    'IncompatibleBaseFieldError',
    'MismatchedIndexSetError',
    'NotKetSpaceError',
    'HilbertSliceError',
]

class HilbertError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg

    def __str__(self):
        return repr(self.msg)

class MismatchedIndexSetError(HilbertError):
    def __init__(self, msg):
        HilbertError.__init__(self, msg)

class DuplicatedSpaceError(HilbertError):
    def __init__(self, spaces, msg=None):
        if msg is None:
            msg = repr(spaces)
        else:
            msg = msg+': '+repr(spaces)
        HilbertError.__init__(self, msg)

class BraKetMixtureError(HilbertError):
    def __init__(self, msg):
        HilbertError.__init__(self, msg)

class HilbertIndexError(HilbertError, LookupError):
    def __init__(self, msg):
        HilbertError.__init__(self, msg)
        LookupError.__init__(self, )

class IncompatibleBaseFieldError(HilbertError):
    def __init__(self, msg):
        HilbertError.__init__(self, msg)

class HilbertShapeError(HilbertError, ValueError):
    def __init__(self, shape1, shape2):
        msg = repr(shape1)+' vs. '+repr(shape2)
        HilbertError.__init__(self, msg)
        ValueError.__init__(self, )

class NotKetSpaceError(HilbertError):
    def __init__(self, msg):
        HilbertError.__init__(self, msg)

class HilbertSliceError(HilbertError):
    def __init__(self, msg):
        HilbertError.__init__(self, msg)
