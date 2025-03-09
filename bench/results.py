from __future__ import annotations

import csv
import dataclasses
import os
import sys
from collections.abc import Sequence
from types import TracebackType
from typing import Any
from typing import cast
from typing import ClassVar
from typing import Generic
from typing import NamedTuple
from typing import overload
from typing import Protocol
from typing import runtime_checkable
from typing import TypeVar
from typing import Union

if sys.version_info >= (3, 11):  # pragma: >=3.11 cover
    from typing import Self
else:  # pragma: <3.11 cover
    from typing_extensions import Self

from pydantic import BaseModel


def make_parent_dirs(filepath: str) -> None:
    """Make parent directories of a filepath."""
    parent_dir = os.path.dirname(filepath)
    if len(parent_dir) > 0 and not os.path.isdir(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)


# https://github.com/python/mypy/issues/14029
# for mypy >=0.990
@runtime_checkable
class NewDataClassProtocol(Protocol):
    """Dataclass Protocol Type."""

    __dataclass_fields__: ClassVar[dict[str, Any]]


@runtime_checkable
class NamedTupleProtocol(Protocol):
    """NamedTuple Protocol Type."""

    _fields: tuple[str, Any]

    def _asdict(self) -> dict[str, Any]: ...


DTYPE_contra = TypeVar(
    'DTYPE_contra',
    bound=Union[BaseModel, NewDataClassProtocol, NamedTuple],
    contravariant=True,
)


class ResultLogger(Protocol[DTYPE_contra]):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None: ...

    def log(self, data: DTYPE_contra) -> None: ...

    def close(self) -> None: ...


class BasicResultLogger(Generic[DTYPE_contra]):
    def __init__(self, _data_type: type[DTYPE_contra]) -> None:
        self.results: list[DTYPE_contra] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.close()

    def log(self, data: DTYPE_contra) -> None:
        self.results.append(data)

    def close(self) -> None:
        pass


class CSVResultLogger(Generic[DTYPE_contra]):
    """CSV logger where rows are represented as a NamedTuple."""

    def __init__(self, filepath: str, data_type: type[DTYPE_contra]) -> None:
        """Init CSVResultLogger."""
        has_headers = False
        fields = field_names(data_type)
        if os.path.isfile(filepath):
            with open(filepath) as f:
                header_row = f.readline()
                headers = [h.strip() for h in header_row.split(',')]
                if header_row != '' and set(headers) != set(fields):
                    raise ValueError(
                        f'File {filepath} already exists and its headers '
                        f'do not match {fields}. Got {headers}.',
                    )
                if header_row != '':
                    has_headers = True

        make_parent_dirs(filepath)
        self.f = open(filepath, 'a', newline='')  # noqa: SIM115
        self.filepath = filepath
        self.writer = csv.DictWriter(self.f, fieldnames=fields)
        if not has_headers:
            self.writer.writeheader()

    def __enter__(self) -> CSVResultLogger[DTYPE_contra]:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exception_type: Any,
        exception_value: Any,
        traceback: Any,
    ) -> None:
        """Exit context manager."""
        self.close()

    def log(self, data: DTYPE_contra) -> None:
        """Log new row."""
        if isinstance(data, BaseModel):
            self.writer.writerow(data.model_dump())
        elif dataclasses.is_dataclass(data) and not isinstance(data, type):
            self.writer.writerow(dataclasses.asdict(data))
        elif isinstance(data, NamedTupleProtocol):
            cast(NamedTupleProtocol, data)
            self.writer.writerow(data._asdict())
        else:
            raise AssertionError
        self.f.flush()

    def close(self) -> None:
        """Close file handles."""
        self.f.close()


@overload
def field_names(data_type: type[DTYPE_contra]) -> Sequence[str]: ...


@overload
def field_names(data_type: DTYPE_contra) -> Sequence[str]: ...


def field_names(data_type: DTYPE_contra | type[DTYPE_contra]) -> Sequence[str]:
    """Extract field names from NamedTuple or Dataclass."""
    if isinstance(data_type, (BaseModel, type(BaseModel))):
        return list(data_type.model_fields.keys())
    elif dataclasses.is_dataclass(data_type):
        return [f.name for f in dataclasses.fields(data_type)]
    elif isinstance(data_type, NamedTupleProtocol):
        return data_type._fields
    else:
        raise AssertionError
