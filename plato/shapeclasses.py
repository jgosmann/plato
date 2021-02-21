from copy import deepcopy
from dataclasses import dataclass, is_dataclass, make_dataclass, Field
from typing import Any, ClassVar
from weakref import WeakKeyDictionary

from .context import get_root
from .providers import Provider


class _ShapeclassProvider(type):
    def sample(self, context):
        return self()


Provider.register(_ShapeclassProvider)


post_sample_registry = WeakKeyDictionary()


def shapeclass(cls):
    fields = []
    post_init_fns = {}
    for name, type_ in cls.__annotations__.items():
        if name in cls.__dict__:
            continue
        if (
            hasattr(type_, "__origin__")
            and getattr(type_, "__origin__") is ClassVar[Any].__origin__
        ):
            continue
        fields.append((name, type_))

    for name, value in cls.__dict__.items():
        if (
            name not in cls.__annotations__
            and not isinstance(value, Field)
            and not isinstance(value, StaticProperty)
        ):
            continue
        type_ = cls.__annotations__.get(name, None)
        if (
            type_ is not None
            and hasattr(type_, "__origin__")
            and getattr(type_, "__origin__") is ClassVar[Any].__origin__
        ):
            continue
        if type_ is None:
            type_ = Any
        if isinstance(value, StaticProperty):
            post_init_fns[name] = value.fn
            value = None
        fields.append((name, type_, value))

    dc = make_dataclass(
        cls.__name__,
        fields,
        bases=cls.__mro__,
    )  # FIXME fill namespace

    post_sample_registry[dc] = post_init_fns

    return dc


def sample(shape, context=None):
    if context is None:
        context = get_root()

    if isinstance(shape, Provider):
        return shape.sample(context)

    x = deepcopy(shape)
    context = context.subcontext(x.__class__.__name__)

    for field_name in x.__annotations__:
        type_ = x.__annotations__.get(field_name, ClassVar[Any])
        if (
            hasattr(type_, "__origin__")
            and getattr(type_, "__origin__") is ClassVar[Any].__origin__
        ):
            continue
        field = getattr(x, field_name)
        if is_dataclass(field):
            value = sample(
                field, context.subcontext(field_name)
            )  # FIXME field vs class name?
            setattr(x, field_name, value)
        elif isinstance(field, Provider):
            value = field.sample(context.subcontext(field_name))
            setattr(x, field_name, value)
    for field_name in dir(x):
        if field_name in x.__annotations__ or field_name in x.__class__.__dict__:
            continue
        if field_name == "__class__":
            continue
        field = getattr(x, field_name)
        if is_dataclass(field):
            value = sample(
                field, context.subcontext(field_name)
            )  # FIXME field vs class name?
            setattr(x, field_name, value)
        elif isinstance(field, Provider):
            value = field.sample(context.subcontext(field_name))
            setattr(x, field_name, value)

    if shape.__class__ in post_sample_registry:
        for name, fn in post_sample_registry[shape.__class__].items():
            setattr(x, name, sample(fn(x), context.subcontext(name)))
    return x


class StaticProperty:
    def __init__(self, fn):
        self.fn = fn


# TODO test
def staticProperty(fn):
    return StaticProperty(fn)