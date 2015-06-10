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

"""Exception classes used by docker-cleanup"""

import traceback


def truncate(s, length):
    """Truncate a string to a specific length

    The result string is never longer than ``length``.
    Appends '..' if truncation occurred.
    """

    return (s[:length - 2] + '..') if len(s) > length else s


class DockerError(Exception):
    """An exception class for errors encountered while calling Docker

    Attributes:
        message (str): The error message.
    """

    def __init__(self, message, *args, **kwargs):
        """Create a DockerError class

        Arguments:
            message (str): The error message.
        """
        super().__init__(message, *args, **kwargs)
        self.message = message


class RulesError(Exception):
    """A generic baseclass for rule-related exceptions

    Attributes:
        message (str): The error message.
        token (TokenInfo): The token around which the error occurred.
        lines (List[str]): The contents of the rules file, if available,
                           otherwise ``None``.
        rulesfilename (Optional[str]): The filename of the rules file, if
                                       available, otherwise ``None``.
    """

    def __init__(self, message, token, lines=None, *args, **kwargs):
        """Create a RulesError class

        Arguments:
            message (str): The error message.
            token (TokenInfo): The token around which the error occurred.
            lines (Optional[List[str]]): The contents of the rules file, if
                                         available.
        """
        super().__init__(message, token, lines, *args, **kwargs)
        self.message = message
        self.token = token
        self.lines = lines
        self.rulefilename = None

    @property
    def lineno(self):
        """The line-number in the input file where the error occurred."""
        return self.token.start[0]

    def print_error(self, dockerobj, rulesfile, file):
        """Print a user-friendly error message to ``file``

        Arguments:
            dockerobj (Optional[Union[Container, Image]]):
              A container or image that was being processed while the
              exception occurred. May be ``None`` if there is no such object.
            rulesfile (str): The rules file name.
            file (File): The file to print the error message to.
        """

        prefix = "%s:%d:%d:" % (rulesfile,
                                self.token.start[0],
                                self.token.start[1])
        print(prefix, "Error parsing rules:", self.message, file=file)
        print(prefix, "  " + self.token.line, file=file)
        print(prefix, "  " + " " * self.token.start[1] + "^", file=file)

        if dockerobj:
            print(prefix, "While processing %s." % str(dockerobj),
                  file=file)


class RuleParseError(RulesError):
    """An rule parsing error exception class"""
    pass


class RuleExecutionError(RulesError):
    """An rule execution error exception class"""
    def _stringify_args(self, args, trunc=50):
        """Turn a list of objects into a list of strings"""
        result = []
        for arg in args:
            try:
                result.append(str(arg))
                continue
            except Exception:
                pass

            try:
                result.append(repr(arg))
                continue
            except Exception:
                pass
            result.append('<unprintable argument>')

        return [truncate(s, trunc) for s in result]

    def _print_traceback(self, prefix, tb, file):
        """Print traceback with as much relevant information as possible

        Neither the Python interpreter nor the ``traceback`` module can
        print the contents of a statement executed via ``eval()`` in a
        trackeback.

        Work around this and display useful error messages to users.
        """

        for fname, lineno, func, text in traceback.extract_tb(tb):
            if not text and fname == self.rulefilename and self.lines:
                try:
                    text = self.lines[lineno - 1]
                except IndexError:
                    pass

            if func == '<module>':
                print(prefix, "File %r, line %d:" % (fname, lineno), file=file)
            else:
                print(prefix,
                      "File %r, line %d in %s:" % (fname, lineno, func),
                      file=file)
            print(prefix, '  ', text, file=file)

    def print_error(self, dockerobj, rulesfile, file):
        """Print a user-friendly error message to ``file``

        Arguments:
            dockerobj (Optional[Union[Container, Image]]):
              A container or image that was being processed while the
              exception occurred. May be ``None`` if there is no such object.
            rulesfile (str): The rules file name.
            file (File): The file to print the error message to.
        """

        if not self.__cause__:
            return super().print_error(dockerobj, rulesfile, file)

        prefix = "%s:%d:" % (rulesfile, self.token.start[0])
        valid_colno = bool(self.token.start[1])
        if valid_colno:
            prefix += "%d:" % self.token.start[1]

        err = self.__cause__
        errname = type(err).__name__
        if dockerobj:
            print(prefix, "%s while processing %s." %
                                (errname, str(dockerobj)), file=file)
        else:
            print(prefix, "%s executing rules:" % errname, file=file)

        # The first traceback level is the eval() statement -- skip it.
        self._print_traceback(prefix, err.__traceback__.tb_next, file)

        args = ', '.join(self._stringify_args(err.args))
        print(prefix, "%s:" % errname, args, file=file)

