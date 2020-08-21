# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import abc
import ast
from pathlib import Path
from pickle import PicklingError
from typing import Collection, Optional, Sequence, Union

import libcst as cst

from fixit.common.autofix import LintPatch


class BaseLintRuleReport(abc.ABC):
    """
    Represents a lint violation. This is generated by calling `self.context.report`
    in your lint rule, and is saved to the context's `reports` list.
    """

    file_path: Path
    code: str
    message: str
    # This is the line/column where the lint rule reported the violation. `arc lint` may
    # report a different line/column when a patch is applied because it requires that
    # the start of the patch is the same as the reported line/column.
    line: int
    column: int

    def __init__(
        self, *, file_path: Path, code: str, message: str, line: int, column: int
    ) -> None:
        self.file_path = file_path
        self.code = code
        self.message = message
        self.line = line
        self.column = column

    @property
    def patch(self) -> Optional[LintPatch]:
        return None

    def __repr__(self) -> str:
        return f"{self.line}:{self.column}: {self.code} {self.message}"

    def __reduce__(self) -> None:
        raise PicklingError(
            "Lint rule reports are potentially very complex objects. They can contain "
            + "a syntax tree or an entire module's source code. They should not be "
            + "pickled (or returned by a multiprocessing worker). Instead, extract "
            + "the fields you care about, and pickle those."
        )


class AstLintRuleReport(BaseLintRuleReport):
    def __init__(
        self,
        *,
        file_path: Path,
        node: ast.AST,
        code: str,
        message: str,
        line: int,
        column: int,
    ) -> None:
        super().__init__(
            file_path=file_path, code=code, message=message, line=line, column=column
        )
        self.node = node


class CstLintRuleReport(BaseLintRuleReport):
    def __init__(
        self,
        *,
        file_path: Path,
        node: cst.CSTNode,
        code: str,
        message: str,
        line: int,
        column: int,
        module: cst.MetadataWrapper,
        module_bytes: bytes,
        replacement_node: Optional[Union[cst.CSTNode, cst.RemovalSentinel]] = None,
    ) -> None:
        super().__init__(
            file_path=file_path, code=code, message=message, line=line, column=column
        )
        self.node = node
        self.module = module
        self.module_bytes = module_bytes
        self.replacement_node = replacement_node
        self._cached_patch: Optional[LintPatch] = None

    # Ideally this would use functools.cached_property, but that's only in py3.8+.
    @property
    def patch(self) -> Optional[LintPatch]:
        """
        Computes and returns a `LintPatch` object.
        """
        replacement_node = self.replacement_node
        if replacement_node is None:
            return None
        cached = self._cached_patch
        if cached is None:
            cached = LintPatch.get(
                wrapper=self.module,
                original_node=self.node,
                replacement_node=replacement_node,
            ).minimize()
            self._cached_patch = cached
        return cached


class LintFailureReportBase(abc.ABC):
    """An implementation needs to be a dataclass."""

    @staticmethod
    @abc.abstractmethod
    def create_reports(
        path: Path, exception_traceback: str, **kwargs: object
    ) -> Sequence["LintFailureReportBase"]:
        ...


class LintSuccessReportBase(abc.ABC):
    """An implementation needs to be a dataclass."""

    @staticmethod
    @abc.abstractmethod
    def create_reports(
        path: Path, reports: Collection[BaseLintRuleReport], **kwargs: object
    ) -> Sequence["LintSuccessReportBase"]:
        ...
