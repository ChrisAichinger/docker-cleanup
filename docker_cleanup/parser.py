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

"""A tokenizer and parser for docker_cleanup rules

For a description of the syntax see the rules-syntax documentation page.
The following text discusses implementation details.

Rule file parsing is done by recursive descent and is implemented across three
classes:

* ``Parser``: tokenization and driver of the parsing process
* ``ImportStatement``: parser for IMPORT statements
* ``ExpressionStatement``: parser for KEEP and DELETE statements

This parser uses the facilities provided by Python as much as possible.
Tokenization is performed using the ``tokenize`` module, which was originally
intended for parsing the Python language, but is flexible enough to be useful
here. ``ImportStatement`` and ``ExpressionStatement`` handle the top-level
language statements, scanning until a semicolon or until an error condition
is reached.

``ImportStatement`` records the package names to import.

``ExpressionStatement`` records the action (keep/delete), type
(container/image), and the following token stream, which can later be executed
using the ``tokenrunner`` module.
"""


import io
import re
import tokenize

from .error import RuleParseError


def is_name_token(token, name):
    """Check if a token is a NAME and has a specific string value

    NAME tokens are returned by the ``tokenize`` module for identifiers
    and keywords: ``if``, ``lambda``, ``a_variable``, ``is_name_token``, ...

    Arguments:
        token (tokenize.TokenInfo): The Token to check.
        name (Union[str, Iterable[str]]): A token name or names to check
                                          against; must be lowercase.

    Returns:
        Return ``True`` if token is a ``NAME`` token and case-insensitively
        matches ``name``. If ``name`` is a tuple or set, return ``True`` if the
        token matches any of the supplied names.

        Return ``False`` otherwise.
    """

    if isinstance(name, str):
        name = set([name])
    return token.exact_type == tokenize.NAME and token.string.lower() in name


class Statement:
    """Parser for a statement

    Attributes:
        start_token (tokenize.TokenInfo): The first token of the statement.
    """

    @classmethod
    def try_parse(cls, tokens):
        """Try to parse a statement

        Arguments:
            tokens (List[tokenize.TokenInfo]): The token stream to parse.

        Returns:
            A ``Statement`` instance if ``tokens`` contains an valid statement,
            otherwise ``None``.

        Raises:
            RuleParseError: Raised if a statement is recognized, but it is
              malformed.
        """

        raise NotImplementedError('Must be implemented in deriving classes')


class ImportStatement(Statement):
    """Parser for an IMPORT statement

    Attributes:
        imports (List[str]): A list of imported modules.
          The strings may include submodules as well (e.g. ``urllib.request``).
        start_token (tokenize.TokenInfo): The first token of the statement.
    """

    KEYWORDS = set(['import'])

    def __init__(self, tokens):
        """Parse an IMPORT statement

        Arguments:
            tokens (List[tokenize.TokenInfo]): The token stream to parse.

        Raises:
            RuleParseError: Raised when a parse error occurs.
        """

        self.imports = []
        self.start_token = tokens.pop(0)
        if not is_name_token(self.start_token, self.KEYWORDS):
            raise RuleParseError("Not an IMPORT statement", self.start_token)

        found_semi = False
        require_name = True
        current_import = []
        while tokens and tokens[0].type != tokenize.ENDMARKER:
            t = tokens.pop(0)
            if t.exact_type == tokenize.SEMI:
                if current_import:
                    self.imports.append('.'.join(current_import))
                found_semi = True
                break

            if require_name and t.exact_type == tokenize.NAME:
                current_import.append(t.string)
                require_name = False
                continue

            if not require_name and t.exact_type == tokenize.DOT:
                require_name = True
                continue

            if not require_name and t.exact_type == tokenize.COMMA:
                self.imports.append('.'.join(current_import))
                current_import = []

                require_name = True
                continue

            if t.exact_type in (tokenize.NL, tokenize.NEWLINE):
                raise RuleParseError("IMPORT statement missing ';'", t)

            raise RuleParseError("Malformed IMPORT statement", t)

        if not found_semi:
            raise RuleParseError("IMPORT statement not terminated with ';'",
                                 self.start_token)

        if not self.imports:
            raise RuleParseError("Empty IMPORT statement", self.start_token)

    @classmethod
    def try_parse(cls, tokens):
        """Try to parse an IMPORT statement

        Arguments:
            tokens (List[tokenize.TokenInfo]): The token stream to parse.

        Returns:
            An ``ImportStatement`` instance if ``tokens`` contains an IMPORT
            statement, otherwise ``None``.

        Raises:
            RuleParseError: Raised if there is an IMPORT statement, but it is
              malformed.
        """

        t = tokens[0]
        if is_name_token(t, cls.KEYWORDS):
            return cls(tokens)
        return None


class ExpressionStatement(Statement):
    """Parser for KEEP and DELETE statements

    Attributes:
        action (str): Either 'keep' or 'delete'.
        type (str): Either 'container' or 'image'.
        force (bool): ``True`` if this is a FORCE KEEP or FORCE DELETE.
        expr (List[tokenize.TokenInfo]): The token stream for the IF
                                         expression.
        start_token (tokenize.TokenInfo): The first token of the statement.
    """

    KEYWORDS = set(['keep', 'delete'])

    def __init__(self, tokens):
        """Parse a KEEP or DELETE statement

        Arguments:
            tokens (List[tokenize.TokenInfo]): The token stream to parse.

        Raises:
            RuleParseError: Raised if the statement can not be parsed.
        """

        self.force = False

        t = self.start_token = tokens.pop(0)
        if is_name_token(t, 'force'):
            self.force = True
            t = tokens.pop(0)

        if not is_name_token(t, self.KEYWORDS):
            raise RuleParseError("Not a valid expression statement", t)
        self.action = t.string.lower()
        self._action = self.action.upper()

        t = tokens.pop(0)
        if t.exact_type != tokenize.NAME:
            raise RuleParseError(
                "%s is missing CONTAINER or IMAGE keyword" % self._action, t)

        if t.string.lower() not in ('container', 'image'):
            raise RuleParseError(
                    "Invalid keyword after %s "
                    "(must be CONTAINER or IMAGE)" % self._action, t)

        self.type = t.string.lower()

        t = tokens.pop(0)
        if not is_name_token(t, 'if'):
            raise RuleParseError(
                "%s statement missing IF keyword" % self._action, t)

        found_semi = False
        self.expr = []
        while tokens:
            t = tokens.pop(0)
            if t.exact_type == tokenize.SEMI:
                found_semi = True
                break

            keywords = self.KEYWORDS | ImportStatement.KEYWORDS
            if is_name_token(t, keywords):
                raise RuleParseError("Invalid keyword in %s statement. "
                                     "Missing semicolon?" % self._action, t)

            if t.exact_type == tokenize.ERRORTOKEN:
                if t.string[0] == ' ':
                    # For some inputs ("x == §"), two error tokens are
                    # generated, one for the blank before the sign, and
                    # one for the paragraph itself.
                    # It's the latter that actually gives useful info.
                    if tokens and tokens[0].exact_type == tokenize.ERRORTOKEN:
                        t = tokens.pop(0)

                if t.string[0] in "'\"":
                    raise RuleParseError("EOL while scanning string", t)
                else:
                    raise RuleParseError("Invalid character in identifier", t)

            self.expr.append(t)

        if not found_semi:
            raise RuleParseError(
                    "%s statement not terminated with ';'" % self._action,
                    self.start_token)

        if not self.expr:
            raise RuleParseError("Empty %s statement" % self._action,
                                 self.start_token)


    @classmethod
    def try_parse(cls, tokens):
        """Try to parse a KEEP or DELETE statement

        Arguments:
            tokens (List[tokenize.TokenInfo]): The token stream to parse.

        Returns:
            An ``ExpressionStatement`` instance if ``tokens`` contains a KEEP
            or DELETE statement, otherwise ``None``.

        Raises:
            RuleParseError: Raised if there is a KEEP or DELETE statement, but
                            it is malformed.
        """

        t0 = tokens[0]
        if is_name_token(t0, cls.KEYWORDS):
            return cls(tokens)

        if len(tokens) < 2:
            return None

        t1 = tokens[1]
        if is_name_token(t0, 'force') and is_name_token(t1, cls.KEYWORDS):
            return cls(tokens)

        return None

    def __str__(self):
        """Return a string representation of the parsed input statement"""
        expr = tokenize.untokenize(self.expr).strip()
        expr = re.sub(r'\s*\\?\n\s*', ' ', expr)
        expr = re.sub(r'\s+', ' ', expr)
        result = ['FORCE'] if self.force else []
        result.extend([self._action, self.type.upper(), 'IF', expr])
        return ' '.join(result)


class Parser:
    """Parser for docker-cleanup rules

    Attributes:
        lines (List[str]): The input string, split into lines.
        statements (List[Statement]): The parsed ``Statement`` objects.
        encoding (str): The guessed encoding of the input string.
    """

    def __init__(self, string):
        """Parse docker-cleanup rules

        Arguments:
            string (str): The input string.

        Raises:
            RuleParseError: Raised if the input string could not be parsed.
        """

        self._tokens = []
        self.lines = string.split('\n')

        bio = io.BytesIO(string.encode('utf-8'))
        tokengen = tokenize.tokenize(bio.readline)
        try:
            # Build the list manually to get access to the partially parsed
            # data in case of a TokenError.
            for t in tokengen:
                self._tokens.append(t)
        except tokenize.TokenError as e:
            raise self._parseerror_from_tokenerror(e) from e

        self._parse_all()


    def _find_unmatched_paren(self):
        """Find unmatched parens in the token stream

        The ``tokenizer`` module errors out if there are unmatched parens in
        the input. Search the already available tokens for unmatched parens
        to give a more descriptive error message.

        Returns:
            A ``tokenize.TokenInfo`` object if an unmatched paren is found,
            otherwise ``None``.
        """

        # No need to differentiate between (, [ and {; tokenize doesn't care.
        stack = []
        for t in self._tokens:
            if t.type == tokenize.OP and t.string in '([{':
                stack.append(t)
            if t.type == tokenize.OP and t.string in ')]}':
                if not stack:
                    return t  # Unmatched close paren
                stack.pop()

        if stack:
            return stack[-1]  # Unmatched open paren

        return None

    def _parseerror_from_tokenerror(self, err):
        """Create a RuleParseError from a ``tokenize.TokenError`` instance"""
        msg, (lineno, colno) = err.args

        if msg == "EOF in multi-line statement" and lineno >= len(self.lines):
            unmatched = self._find_unmatched_paren()
            if unmatched:
                lineno, colno = unmatched.start

        try:
            line = self.lines[lineno - 1]
        except IndexError:
            line = ''
        try:
            string = line[colno]
        except IndexError:
            string = ''

        et = tokenize.TokenInfo(tokenize.ERRORTOKEN,
                                string,
                                (lineno, colno),
                                (lineno, colno + 1),
                                line)
        return RuleParseError('Tokenizer error: %s' % msg, et, self.lines)

    def _parse_all(self):
        """Parse the whole input token stream"""
        self.statements = []

        while self._tokens:
            if self._tokens[0].type == tokenize.ENCODING:
                self.encoding = self._tokens.pop(0).string
                continue
            if self._tokens[0].exact_type in (tokenize.NL, tokenize.NEWLINE):
                self._tokens.pop(0)
            self._parse_statement()

    def _parse_statement(self):
        """Parse a single statement in the token stream"""
        ignore_tokens = (tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
                         tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                         )
        if self._tokens[0].exact_type in ignore_tokens:
            self._tokens.pop(0)
            return

        for cls in [ImportStatement, ExpressionStatement]:
            try:
                smt = cls.try_parse(self._tokens)
            except RuleParseError as e:
                # Statement classes don't have the input lines, add them here.
                e.lines = self.lines
                raise

            if smt is not None:
                self.statements.append(smt)
                return

        raise RuleParseError("Not a valid statement",
                             self._tokens[0], self.lines)
