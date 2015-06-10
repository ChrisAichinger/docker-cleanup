# Copyright 2015 Christian Aichinger <Greek0@gmx.net>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Evaluate a stream of ``tokenize`` tokens

Provides the ``Executor`` class to compile and run a ``tokenize.TokenInfo``
stream, returning the result.
"""

import sys
import ast
import tokenize

from .error import RuleExecutionError


class Executor:
    """Execute a token stream and return the result

    On creation, the input tokens are compiled with ``compile()``. When
    ``run()`` is called, the compiled code is executed and the result is
    returned.

    Attributes:
        input_tokens (List[TokenInfo]): The input token stream.
        input_lines (List[str]): A stringized version of the input token
                                 stream, split into lines.
        filename (str): The input filename. May be ``"<unknown>"``.
        line_offset (int): An offset of tokens within the input file.
                           Typically zero, as the tokens know what line they
                           were on.
        eval_tokens (List[TokenInfo]): A processed version of the
                                       token stream.
        eval_str (List[str]): A stringized version of the processed token
                              stream.
        codeobj (code): The compiled code object.
    """

    def __init__(self, tokens, filename='<unknown>', line_offset=0):
        """Create an executor for a token stream

        Arguments:
            tokens (List[TokenInfo]): The tokens to execute.
            filename (Optional[str]): The filename where the tokens originated
                                      (default: ``'<unknown>'``).
                                      Used in error handling, but never opened.
            line_offset (Optional[str]): An offset of tokens within the input
                                         file (default: zero).

        Raises:
            RuleExecutionError: Raised if the token stream is invalid or if
                                it could not be compiled.
        """

        self.input_tokens = tokens
        self.input_lines = tokenize.untokenize(self.input_tokens).split('\n')
        self.filename = filename
        self.line_offset = line_offset

        self._validate_paren_levels(tokens)
        self.eval_tokens = self._gen_eval_tokens(tokens)
        self.eval_str = tokenize.untokenize(self.eval_tokens)
        self.codeobj = self._compile(self.eval_str)

    def _offset_token(self, t):
        """Offset the position of ``t`` by ``line_offset``

        Arguments:
            t (TokenInfo): The input token.
        Returns:
            A new ``TokenInfo`` instance equal to ``t``, but shifted by
            ``self.line_offset`` lines.
        """

        start = (t.start[0] + self.line_offset, t.start[1])
        end = (t.end[0] + self.line_offset, t.end[1])

        return t._replace(start=start, end=end)

    def _validate_paren_levels(self, tokens):
        """Raise RuleExecutionError if mismatched parens are found

        ``_gen_eval_tokens()`` wraps the input in parens to enable multi-line
        expressions. This causes the following expression to become valid::

            "True) and (True"

        Catch that case by validating that all parens in the input are matched.
        """

        stack = []
        for t in tokens:
            if t.exact_type == tokenize.LPAR:
                stack.append(t)
            elif t.exact_type == tokenize.RPAR:
                if len(stack) == 0:
                    t = self._offset_token(t)
                    raise RuleExecutionError(
                        "Close paren without matching open paren", t,
                        self.input_lines)
                stack.pop()

        if stack:
            t = self._offset_token(stack[-1])
            raise RuleExecutionError("Missing close paren", t,
                                     self.input_lines)

    def _gen_eval_tokens(self, tokens):
        """Wrap tokens in parens so multi-line input works as expected"""

        # untokenize() stops at ENDMARKER, causing rparen to be discarded.
        tokens = [t for t in tokens if t.type != tokenize.ENDMARKER]

        if not tokens:
            tokens = [tokenize.TokenInfo(
                tokenize.NAME, 'None', (1, 0), (1, 4), 'None')]

        last = tokens[-1]
        lparen = tokenize.TokenInfo(tokenize.OP, '(', (1, 0), (1, 0), '(')
        rparen = tokenize.TokenInfo(tokenize.OP, ')', last.end,
                                    (last.end[0], last.end[1] + 1), ')')

        return [lparen] + tokens + [rparen]

    def _compile(self, string):
        """Compile the input string"""
        # Call compile() directly to retain control over __future__ flags.
        tree = compile(string, self.filename, 'eval', ast.PyCF_ONLY_AST)

        ast.increment_lineno(tree, self.line_offset)
        return compile(tree, self.filename, 'eval')

    def run(self, global_vars=None):
        """Run the token stream and return the result

        Arguments:
            global_vars (dict): A ``dict`` of global variables made available
                                to the code being run.

        Returns:
            The result returned by the executed code.

        Raises:
            RuleExecutionError: Raised if an exception occurs while executing
                                the token stream.
        """

        if global_vars is None:
            global_vars = dict()

        try:
            return eval(self.codeobj, global_vars)
        except Exception as e:
            # The first frame is this function, advance into the eval().
            tb = e.__traceback__.tb_next

            # Get the line number from the deepest stack frame that's still
            # from self.filename.
            lineno = self.line_offset
            while tb:
                fname = tb.tb_frame.f_code.co_filename
                if fname == self.filename:
                    lineno = tb.tb_frame.f_lineno

                tb = tb.tb_next

            try:
                line = self.input_lines[lineno]
            except IndexError:
                line = ''

            orig_exception = e  # Helps with debugging inside pdb.
            etype = type(e).__name__
            t = tokenize.TokenInfo(tokenize.ERRORTOKEN, '',
                                   (lineno, 0), (lineno, 0), line)
            raise RuleExecutionError("'%s' exception occurred" % etype,
                                     t, self.input_lines) from e
