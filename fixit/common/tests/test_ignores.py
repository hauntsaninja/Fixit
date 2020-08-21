# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import tokenize
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import Container, Iterable, Tuple

import libcst as cst
from libcst.testing.utils import UnitTest, data_provider

from fixit.common.comments import CommentInfo
from fixit.common.ignores import IgnoreInfo
from fixit.common.line_mapping import LineMappingInfo
from fixit.common.report import CstLintRuleReport


class IgnoreInfoTest(UnitTest):
    @data_provider(
        {
            # A noqa comment can be used without a specified code, which will ignore all
            # lint errors on that line. This is a bad practice, but we have to support
            # it for compatibility with existing code. (until we can codemod it away)
            "noqa_all_legacy": {
                "source": dedent(
                    """\
                    fn1()
                    fn2()  # noqa
                    fn3()
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [2],
            },
            # When a noqa comment is specified with codes, it should only ignore the
            # specified codes.
            "noqa_with_code": {
                "source": dedent(
                    """\
                    fn1()  # noqa: IgnoredRule
                    fn2()  # noqa: IgnoredRule: Message
                    fn3()  # noqa: IgnoredRule, Ignored2Rule: Message
                    fn4()  # noqa: Ignored1Rule
                    fn5()  # noqa: Ignored1Rule, Ignored2Rule
                    fn6()  # noqa: Ignored1Rule, Ignored2Rule: Message
                    """
                ),
                "ignored_code": "Ignored1Rule",
                "ignored_lines": [4, 5, 6],
            },
            "noqa_multiline": {
                "source": dedent(
                    """\
                    fn1(line, \\
                    continuation)  # noqa: IgnoredRule

                    fn2()

                    fn3('''
                        multiline
                        string
                    ''')  # noqa: IgnoredRule
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [1, 2, 6, 7, 8, 9],
            },
            "noqa_file": {
                "source": dedent(
                    """\
                    # noqa-file: IgnoredRule: Some reason
                    fn1()
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [1, 2, 3],
            },
            "noqa_file_multiple_codes": {
                "source": dedent(
                    """\
                    # noqa-file: IgnoredRule, Ignored1Rule, Ignored2Rule: Some reason
                    fn1()
                    """
                ),
                "ignored_code": "Ignored1Rule",
                "ignored_lines": [1, 2, 3],
            },
            "noqa_file_requires_code_and_reason": {
                "source": dedent(
                    """\
                    # noqa-file
                    # noqa-file: IgnoredRule
                    # Neither of these noqa-files should work because they're incomplete
                    fn1()
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [],
            },
            "backwards_compatibility_classname": {
                "source": dedent(
                    """\
                    fn1() # noqa: IG00, IgnoredRule
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [1],
            },
            "backwards_compatibility_oldcode": {
                "source": dedent(
                    """\
                    fn1() # noqa: IG00, IgnoredRule
                    """
                ),
                "ignored_code": "IG00",
                "ignored_lines": [1],
            },
            "lint_fixme": {
                "source": dedent(
                    """\
                    fn1()

                    # lint-fixme: IgnoredRule: Some short reason
                    fn2(  # this line should be ignored
                        "multiple",  # but these lines shouldn't
                        "arguments",
                    )

                    # lint-fixme: IgnoredRule: Some reason spanning
                    # lint: multiple lines because it's long.
                    fn3('''
                        multiline
                        string
                    ''')  # this function call is a single logical line

                    fn4()
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [3, 4, 9, 10, 11, 12, 13, 14],
            },
            "lint_ignore": {
                "source": dedent(
                    """\
                    fn1()

                    # lint-ignore: IgnoredRule: Some reason
                    fn2()

                    fn3()
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [3, 4],
            },
            # A lint-ignore can exist right before an EOF. That's fine. We should ignore
            # all the way to the EOF.
            "lint_ignore_eof": {
                "source": dedent(
                    """\
                    # lint-ignore: IgnoredRule
                    """
                ),
                "ignored_code": "IgnoredRule",
                "ignored_lines": [1, 2],
            },
        }
    )
    def test_ignored_lines(
        self, *, source: str, ignored_code: str, ignored_lines: Container[int]
    ) -> None:
        tokens = tuple(tokenize.tokenize(BytesIO(source.encode("utf-8")).readline))
        ignore_info = IgnoreInfo.compute(
            comment_info=CommentInfo.compute(tokens=tokens),
            line_mapping_info=LineMappingInfo.compute(tokens=tokens),
        )
        lines = range(1, tokens[-1].end[0] + 1)
        actual_ignored_lines = []
        for line in lines:
            ignored = ignore_info.should_ignore_report(
                CstLintRuleReport(
                    file_path=Path("fake/path.py"),
                    node=cst.EmptyLine(),
                    code=ignored_code,
                    message="message",
                    line=line,
                    column=0,
                    module=cst.MetadataWrapper(cst.parse_module(source)),
                    module_bytes=source.encode("utf-8"),
                )
            )
            if ignored:
                actual_ignored_lines.append(line)
        # pyre-fixme[6]: Expected `Iterable[Variable[_T]]` for 1st param but got
        #  `Container[int]`.
        self.assertEqual(actual_ignored_lines, list(ignored_lines))

    @data_provider(
        {
            "unused_noqa": {
                "source": "fn()  # noqa",
                "reports_on_lines": [],
                "unused_comments": [1],
            },
            "used_noqa": {
                "source": "fn()  # noqa",
                "reports_on_lines": [(1, "Ignored999Rule")],
                "unused_comments": [],
            },
            "unused_lint_ignore": {
                "source": "# lint-ignore: Ignored999Rule: Some reason\nfn()",
                "reports_on_lines": [],
                "unused_comments": [1],
            },
            "used_lint_ignore": {
                "source": "# lint-ignore: Ignored999Rule: Some reason\nfn()",
                "reports_on_lines": [(2, "Ignored999Rule")],
                "unused_comments": [],
            },
            "lint_ignore_is_used_before_noqa": {
                "source": "# lint-ignore: Ignored999Rule: Some reason\nfn()  # noqa",
                "reports_on_lines": [(2, "Ignored999Rule")],
                "unused_comments": [2],
            },
            "duplicate_lint_ignores": {
                "source": "# lint-ignore: Ignored999Rule: First\n# lint-ignore: Ignored999Rule: Second\nfn()",
                "reports_on_lines": [(3, "Ignored999Rule")],
                "unused_comments": [2],
            },
        }
    )
    def test_unused_comments(
        self,
        *,
        source: str,
        reports_on_lines: Iterable[Tuple[int, str]],
        unused_comments: Iterable[int],
    ) -> None:
        """
        Verify that we can correctly track which lint comments were used and which were
        unused.

        TODO: We don't track usage of global ignore comments, so we can't know if
        they're unused.
        """
        tokens = tuple(tokenize.tokenize(BytesIO(source.encode("utf-8")).readline))
        ignore_info = IgnoreInfo.compute(
            comment_info=CommentInfo.compute(tokens=tokens),
            line_mapping_info=LineMappingInfo.compute(tokens=tokens),
        )

        for line, code in reports_on_lines:
            ignore_info.should_ignore_report(
                CstLintRuleReport(
                    file_path=Path("fake/path.py"),
                    node=cst.EmptyLine(),
                    code=code,
                    message="message",
                    line=line,
                    column=0,
                    module=cst.MetadataWrapper(cst.parse_module(source)),
                    module_bytes=source.encode("utf-8"),
                )
            )

        self.assertEqual(
            sorted(
                [
                    min(tok.start[0] for tok in c.tokens)
                    for c in ignore_info.suppression_comments
                    if not c.used_by
                ]
            ),
            sorted(unused_comments),
        )
