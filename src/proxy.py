""" This module introduces two decorators - @proxy.stub and @proxy.impl

@proxy.stub is used to decorate a stub method that should be filled in
with an implementation in some other module. Calling the stub method
calls the implementation method in the other module instead of the stub
method itself (or raises a NotImplementedError if no such
implementation exists)

@proxy.impl is used to define a previously-declared stub with an actual
implementation to call -- the signature for the implementation must
exactly match the signature for the stub (enforced for Python 3.3+).

Attempting to implement a non-existent stub is an error, as is trying
to re-implement a stub that is already implemented.

Example:
(foo.py)
@proxy.stub
def my_method(foo, bar=10):
    pass

(bar.py)
@proxy.impl
def my_method(foo, bar=10):
    return foo * bar
"""

import inspect

IMPLS = {}
SIGS = {}

def stub(f):
    def inner(*args, **kwargs):
        _ignore_locals_ = True
        if f.__name__ not in IMPLS:
            raise NotImplementedError(("This proxy stub has not yet been "
                                       "implemented in another module"))
        return IMPLS[f.__name__](*args, **kwargs)

    if f.__name__ in SIGS:
        _sigmatch(f)
    SIGS[f.__name__] = inspect.signature(f)

    return inner

def impl(f):
    if f.__name__ not in SIGS:
        raise NameError(("Attempting to implement a proxy stub {0} that does "
                         "not exist").format(f.__name__))
    if f.__name__ in IMPLS:
        raise SyntaxError(("Attempting to implement a proxy stub {0} that "
                           "already has an implementation").format(f.__name__))
    _sigmatch(f)

    # Always wrap proxy implementations in an error handler
    # proxy needs to be a top level (no dependencies) module, so can't import this
    # up top or else we get loops
    from src.decorators import handle_error
    IMPLS[f.__name__] = handle_error(f)
    # allows this method to be called directly in our module rather
    # than forcing use of the stub's module
    return handle_error(f)

def _sigmatch(f):
    rs = inspect.signature(f)
    ts = SIGS[f.__name__]
    if len(rs.parameters) != len(ts.parameters):
        raise TypeError(
            ("Arity does not match existing stub, "
            "expected {0} parameters but got {1}.").format(
                len(ts.parameters), len(rs.parameters)))
    opl = list(rs.parameters.values())
    tpl = list(ts.parameters.values())
    for i in range(len(rs.parameters)):
        op = opl[i]
        tp = tpl[i]
        if op.name != tp.name:
            raise TypeError(
                ("Parameter name does not match existing stub, "
                "expected {0} but got {1}.").format(tp.name, op.name))
        if op.default != tp.default:
            raise TypeError(
                ("Default value of parameter does not match existing stub "
                "for parameter {0}, expected {1} but got {2}.").format(
                    op.name,
                    ("no default" if tp.default is inspect.Parameter.empty
                                  else repr(tp.default)),
                    ("no default" if op.default is inspect.Parameter.empty
                                  else repr(op.default))))
        if op.kind != tp.kind:
            raise TypeError(
                ("Parameter type does not match existing stub for "
                "parameter {0}, expected {1} but got {2}.").format(
                    op.name, str(tp.kind), str(op.kind)))

# vim: set sw=4 expandtab:
