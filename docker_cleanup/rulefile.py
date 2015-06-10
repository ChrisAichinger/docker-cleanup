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

"""High-level interface to docker-cleanup rules

Provides a ``RuleFile`` class that handles rules parsing and that
checks containers and images against the rules.
"""

import enum
import logging

from . import error, parser, tokenrunner
from .error import truncate

logger = logging.getLogger(__name__)


class RuleAction(enum.Enum):
    """The action to take with a container or image"""
    keep = 0
    delete = 1
    force_delete = 2


class RuleFile:
    """Read a docker-clean rules file and match containers/images against it

    Attributes:
        filename (str): The rule file name, if available (otherwise ``None``).
        contents (str): The rule file contents.
        statements (List[Statement]): The statements contained in the file.
    """

    def __init__(self, f):
        """Load and parse a rules file

        Arguments:
            f (File): The input file object.

        Raises:
            RulesError: May raise a ``RulesError`` subclass if the rules
                        could not be parsed.
        """

        try:
            self.filename = f.name
        except AttributeError:
            self.filename = None

        self.contents = f.read()
        try:
            self.parser = parser.Parser(self.contents)
        except error.RulesError as e:
            logger.info('Error while parsing rules')
            e.rulefilename = self.filename
            raise

        self.statements = self.parser.statements

    def _do_import(self, smt, context):
        """Execute an IMPORT statement"""
        logger.info('  Importing %r', smt.imports)
        for imp in smt.imports:
            exec('import %s' % imp, {}, context)

    def _do_expression(self, smt, context):
        """Execute an expression statement (KEEP or DELETE)"""
        try:
            ex = tokenrunner.Executor(smt.expr, self.filename or '<unknown>')
            return ex.run(dict(context))
        except tokenrunner.RuleExecutionError as e:
            logger.info('    error during statement evaluation')

            # The exception's lines are reconstructed by Executor from
            # its token stream. Replace them with the original version.
            e.rulefilename = self.filename
            e.lines = self.contents.split('\n')
            raise

    def can_delete(self, dockerobj, context=None):
        """Check a container or image against the rules

        Arguments:
            dockerobj (Union[Container, Image): The container/image to test.
            context (Optional[dict]): A set of global variables under which
                                      the rules should be run.

        Returns:
            A ``RuleAction`` value specifying whether the object should be
            kept, deleted or force-deleted.

        Raises:
            RulesError: Raise a ``RulesError`` subclass if a rule could not
                        be executed.
        """

        if context is None:
            context = dict()

        objtype = type(dockerobj).__name__.lower()
        Objtype = objtype.capitalize()
        context[Objtype] = dockerobj

        logger.info('Processing %s %s', objtype, str(dockerobj))
        for smt in self.statements:
            if isinstance(smt, parser.ImportStatement):
                self._do_import(smt, context)
                continue

            if isinstance(smt, parser.ExpressionStatement):
                if smt.type != objtype:
                    logger.info('  Skipping %s', truncate(str(smt), 50))
                    continue

                logger.info('  Evaluating %s', truncate(str(smt), 50))
                smt_matches = self._do_expression(smt, context)
                if not smt_matches:
                    logger.info('    no match, continuing')
                    continue

                logger.info('    match found, triggering %s%s',
                            'FORCE ' if smt.force else '', smt.action.upper())

                if smt.action == 'keep':
                    return RuleAction.keep
                elif smt.action == 'delete':
                    if smt.force:
                        return RuleAction.force_delete
                    return RuleAction.delete
                else:
                    raise NotImplementedError(  # pragma: no cover
                            'Unknown action in ExpressionStatement', smt)

            raise NotImplementedError(  # pragma: no cover
                    'Unknown parser statement', smt)

        return RuleAction.keep
